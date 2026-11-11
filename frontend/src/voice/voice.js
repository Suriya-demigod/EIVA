const listenButton = document.querySelector("#listen");
const stopButton = document.querySelector("#stop");
const statusText = document.querySelector("#status");
const heardText = document.querySelector("#heard");
const answerText = document.querySelector("#answer");

let mediaStream;
let mediaRecorder;
let audioContext;
let animationFrame;
let chunks = [];
let heardSpeech = false;
let lastVoiceAt = 0;
let recordingStartedAt = 0;
let requestController;
let activeAudio;
let conversationId;

function setStatus(message) {
  statusText.textContent = message;
}

function stopMicrophone() {
  cancelAnimationFrame(animationFrame);
  if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
  if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
  mediaStream = undefined;
  if (audioContext && audioContext.state !== "closed") audioContext.close();
  audioContext = undefined;
  listenButton.textContent = "Start speaking";
  stopButton.disabled = true;
}

function stopPlayback() {
  if (requestController) requestController.abort();
  requestController = undefined;
  if (activeAudio) {
    activeAudio.pause();
    activeAudio.removeAttribute("src");
    activeAudio = undefined;
  }
}

async function startListening() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setStatus("This browser does not support microphone recording.");
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]
      .find((candidate) => MediaRecorder.isTypeSupported(candidate));
    if (!mimeType) throw new Error("This browser cannot record a supported audio format.");

    chunks = [];
    heardSpeech = false;
    lastVoiceAt = 0;
    recordingStartedAt = Date.now();
    mediaRecorder = new MediaRecorder(mediaStream, { mimeType });
    mediaRecorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    mediaRecorder.onerror = () => {
      stopMicrophone();
      listenButton.disabled = false;
      setStatus("Microphone recording failed. Check the selected input device and try again.");
    };
    mediaRecorder.onstop = () => {
      if (heardSpeech && chunks.length) submitRecording(new Blob(chunks, { type: mimeType }));
      else {
        listenButton.disabled = false;
        setStatus("No speech detected. Select Start speaking to try again.");
      }
    };
    mediaRecorder.start(250);
    listenButton.disabled = true;
    const source = audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    source.createMediaStreamSource(mediaStream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    listenButton.textContent = "Listening…";
    stopButton.disabled = false;
    setStatus("Listening. Pause for a moment when you finish.");

    const monitor = () => {
      if (!mediaRecorder || mediaRecorder.state === "inactive") return;
      analyser.getByteTimeDomainData(samples);
      let energy = 0;
      for (const sample of samples) {
        const normalized = (sample - 128) / 128;
        energy += normalized * normalized;
      }
      const rms = Math.sqrt(energy / samples.length);
      const now = Date.now();
      if (rms > 0.025) {
        heardSpeech = true;
        lastVoiceAt = now;
      }
      if (heardSpeech && now - lastVoiceAt > 1300) {
        setStatus("Sending your recording for transcription…");
        stopMicrophone();
        return;
      }
      if (now - recordingStartedAt > 18_000) {
        if (heardSpeech) setStatus("Sending your recording for transcription…");
        stopMicrophone();
        return;
      }
      animationFrame = requestAnimationFrame(monitor);
    };
    monitor();
  } catch (error) {
    stopMicrophone();
    listenButton.disabled = false;
    setStatus(error.name === "NotAllowedError" ? "Microphone access was denied." : error.message);
  }
}

async function postJson(url, payload, signal) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const isSpeech = url.endsWith("/voice/speech");
    throw new Error(isSpeech
      ? `EIVA replied in text, but speech generation failed (${response.status}).`
      : `Request failed (${response.status}). Check that voice is enabled and try again.`);
  }
  return response;
}

async function speak(text, signal) {
  const pieces = [];
  let remaining = text.trim();
  while (remaining.length > 200) {
    let boundary = remaining.lastIndexOf(" ", 200);
    if (boundary < 1) boundary = 200;
    pieces.push(remaining.slice(0, boundary).trim());
    remaining = remaining.slice(boundary).trim();
  }
  if (remaining) pieces.push(remaining);
  for (const piece of pieces) {
    const response = await postJson("/api/v1/voice/speech", { text: piece }, signal);
    const objectUrl = URL.createObjectURL(await response.blob());
    activeAudio = new Audio(objectUrl);
    try {
      const finished = new Promise((resolve, reject) => {
        activeAudio.addEventListener("ended", resolve, { once: true });
        activeAudio.addEventListener("error", () => reject(new Error("Audio playback failed.")), { once: true });
        signal.addEventListener("abort", () => reject(new DOMException("Stopped", "AbortError")), { once: true });
      });
      await activeAudio.play();
      await finished;
    } finally {
      activeAudio = undefined;
      URL.revokeObjectURL(objectUrl);
    }
  }
}

async function submitRecording(blob) {
  requestController = new AbortController();
  const { signal } = requestController;
  listenButton.disabled = true;
  stopButton.disabled = false;
  try {
    const transcriptResponse = await fetch("/api/v1/voice/transcribe", {
      method: "POST",
      headers: { "Content-Type": blob.type },
      body: blob,
      signal,
    });
    if (!transcriptResponse.ok) throw new Error(`Transcription failed (${transcriptResponse.status}).`);
    const { text } = await transcriptResponse.json();
    heardText.textContent = text;
    heardText.classList.remove("muted");
    setStatus("Getting EIVA’s response…");

    const chat = await postJson("/api/v1/chat", {
      message: text,
      ...(conversationId ? { conversation_id: conversationId } : {}),
    }, signal);
    const result = await chat.json();
    conversationId = result.conversation_id;
    const answer = result.message.content;
    answerText.textContent = answer;
    answerText.classList.remove("muted");
    setStatus("Speaking EIVA’s response. Select Stop / cancel to interrupt playback.");
    try {
      await speak(answer, signal);
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new Error(`EIVA replied in text, but could not speak the response: ${error.message}`);
    }
    setStatus("Finished. Select Start speaking when you’re ready.");
  } catch (error) {
    if (error.name === "AbortError") setStatus("Voice turn stopped.");
    else setStatus(error.message || "The voice request failed.");
  } finally {
    requestController = undefined;
    activeAudio = undefined;
    listenButton.disabled = false;
    stopButton.disabled = true;
  }
}

listenButton.addEventListener("click", startListening);
stopButton.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    setStatus(heardSpeech ? "Sending your recording for transcription…" : "Stopped. No speech was detected.");
    stopMicrophone();
  } else {
    stopPlayback();
    setStatus("Voice turn stopped.");
  }
});

fetch("/api/v1/voice/status")
  .then((response) => response.json())
  .then(({ enabled }) => {
    if (!enabled) {
      listenButton.textContent = "Voice is disabled";
      setStatus("Set VOICE_ENABLED=true in .env and restart EIVA to enable voice.");
      return;
    }
    listenButton.disabled = false;
    listenButton.textContent = "Start speaking";
    setStatus("Microphone is off. Select Start speaking to begin.");
  })
  .catch(() => setStatus("Could not read EIVA voice settings."));
