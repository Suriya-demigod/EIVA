/* Ruby AI — text chat, voice input, and spoken replies. */
(() => {
  "use strict";

  const API = window.location.origin;
  let sessionId = crypto.randomUUID();
  const $messages = document.getElementById("messages");
  const $input = document.getElementById("message-input");
  const $sendBtn = document.getElementById("send-btn");
  const $voiceBtn = document.getElementById("voice-btn");
  const $voiceSelect = document.getElementById("voice-select");
  const $voiceStatus = document.getElementById("voice-status");
  const $newChat = document.getElementById("new-chat-btn");
  const $themeToggle = document.getElementById("theme-toggle");
  const $sideToggle = document.getElementById("sidebar-toggle");
  const $sidebar = document.getElementById("sidebar");
  const $statusDot = document.querySelector(".status-dot");
  const $statusText = document.getElementById("status-text");

  let isStreaming = false;
  let voiceBusy = false;
  let recorder = null;
  let microphoneStream = null;
  let recordedChunks = [];
  let playbackToken = 0;
  let activePlayback = null;

  const savedTheme = localStorage.getItem("ruby-theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
  const voiceIds = ["autumn", "diana", "hannah", "austin", "daniel", "troy"];
  const savedVoice = localStorage.getItem("ruby-voice") || "troy";
  $voiceSelect.value = voiceIds.includes(savedVoice) ? savedVoice : "troy";
  $voiceSelect.addEventListener("change", () => {
    localStorage.setItem("ruby-voice", $voiceSelect.value);
  });

  $themeToggle.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("ruby-theme", next);
  });
  $sideToggle.addEventListener("click", () => $sidebar.classList.toggle("open"));

  async function checkHealth() {
    try {
      const response = await fetch(`${API}/api/health`);
      if (!response.ok) throw new Error(response.statusText);
      const health = await response.json();
      $statusDot.className = "status-dot status-ok";
      $statusText.textContent = `Online — v${health.version}`;
    } catch {
      $statusDot.className = "status-dot status-error";
      $statusText.textContent = "Offline";
    }
  }
  checkHealth();

  function scrollToBottom() {
    $messages.scrollTo({ top: $messages.scrollHeight, behavior: "smooth" });
  }

  function clearWelcome() {
    const welcome = $messages.querySelector(".welcome");
    if (welcome) welcome.remove();
  }

  function renderMarkdown(text) {
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code class="language-${lang}">${code.trim()}</code></pre>`);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
    return html.replace(/\n/g, "<br>");
  }

  function addMessage(role, content) {
    clearWelcome();
    const row = document.createElement("div");
    row.className = `message-row ${role}`;
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "👤" : "💎";
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = renderMarkdown(content);
    row.append(avatar, bubble);
    $messages.appendChild(row);
    scrollToBottom();
    return bubble;
  }

  function addTypingIndicator() {
    clearWelcome();
    const row = document.createElement("div");
    row.className = "message-row assistant";
    row.id = "typing-row";
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "💎";
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    row.append(avatar, bubble);
    $messages.appendChild(row);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    document.getElementById("typing-row")?.remove();
  }

  function updateButtons() {
    $sendBtn.disabled = !$input.value.trim() || isStreaming;
    const recording = recorder?.state === "recording";
    $voiceBtn.disabled = (!recording && (isStreaming || voiceBusy)) || !navigator.mediaDevices?.getUserMedia;
  }

  function splitSpeechText(source, maxChars = 180) {
    const text = source
      .replace(/```[\s\S]*?```/g, "Code block omitted.")
      .replace(/[`*_>#]/g, "")
      .replace(/\s+/g, " ")
      .trim();
    const chunks = [];
    let current = "";
    for (const word of text.split(" ")) {
      if (Array.from(word).length > maxChars) {
        if (current) chunks.push(current), current = "";
        const chars = Array.from(word);
        for (let i = 0; i < chars.length; i += maxChars) chunks.push(chars.slice(i, i + maxChars).join(""));
        continue;
      }
      const next = current ? `${current} ${word}` : word;
      if (Array.from(next).length > maxChars) {
        chunks.push(current);
        current = word;
      } else current = next;
    }
    if (current) chunks.push(current);
    return chunks;
  }

  function resetPlaybackControls(controls, status = "") {
    if (!controls) return;
    controls.pause.disabled = true;
    controls.pause.textContent = "Pause";
    controls.stop.disabled = true;
    controls.status.textContent = status;
  }

  function stopActivePlayback() {
    playbackToken += 1;
    if (activePlayback) {
      const old = activePlayback;
      old.cancel?.();
      old.audio?.pause();
      if (old.url) URL.revokeObjectURL(old.url);
      resetPlaybackControls(old.controls, "Stopped");
      activePlayback = null;
    }
  }

  async function playSpeech(text, controls) {
    stopActivePlayback();
    const token = playbackToken;
    const state = { token, audio: null, url: null, controls, cancel: null };
    activePlayback = state;
    controls.status.textContent = "Preparing speech…";
    controls.stop.disabled = false;

    try {
      const chunks = splitSpeechText(text);
      for (let index = 0; index < chunks.length; index += 1) {
        if (token !== playbackToken) return;
        const response = await fetch(`${API}/api/voice/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: chunks[index], voice: $voiceSelect.value }),
        });
        if (!response.ok) {
          let message = `Speech service returned ${response.status}.`;
          try { message = (await response.json()).detail || message; } catch { /* keep fallback */ }
          throw new Error(message);
        }
        const audioBlob = await response.blob();
        if (token !== playbackToken) return;
        const url = URL.createObjectURL(audioBlob);
        const audio = new Audio(url);
        state.audio = audio;
        state.url = url;
        controls.status.textContent = `Speaking ${index + 1}/${chunks.length}`;
        controls.pause.disabled = false;
        await new Promise((resolve, reject) => {
          state.cancel = resolve;
          audio.addEventListener("ended", resolve, { once: true });
          audio.addEventListener("error", () => reject(new Error("Audio playback failed.")), { once: true });
          audio.play().catch(reject);
        });
        URL.revokeObjectURL(url);
        state.audio = null;
        state.url = null;
        state.cancel = null;
      }
      if (token === playbackToken) controls.status.textContent = "Finished";
    } catch (error) {
      if (token === playbackToken) controls.status.textContent = `Audio error: ${error.message}`;
    } finally {
      if (token === playbackToken) {
        resetPlaybackControls(controls, controls.status.textContent);
        activePlayback = null;
      }
    }
  }

  function addSpeechControls(bubble, text) {
    const controlsElement = document.createElement("div");
    controlsElement.className = "speech-controls";
    const play = document.createElement("button");
    play.type = "button";
    play.textContent = "🔊 Listen";
    const pause = document.createElement("button");
    pause.type = "button";
    pause.textContent = "Pause";
    pause.disabled = true;
    const stop = document.createElement("button");
    stop.type = "button";
    stop.textContent = "Stop";
    stop.disabled = true;
    const status = document.createElement("span");
    controlsElement.append(play, pause, stop, status);
    bubble.appendChild(controlsElement);
    const controls = { pause, stop, status };
    play.addEventListener("click", () => playSpeech(text, controls));
    pause.addEventListener("click", async () => {
      if (activePlayback?.controls !== controls || !activePlayback.audio) return;
      if (activePlayback.audio.paused) {
        try {
          await activePlayback.audio.play();
          pause.textContent = "Pause";
          status.textContent = "Speaking…";
        } catch (error) { status.textContent = `Audio error: ${error.message}`; }
      } else {
        activePlayback.audio.pause();
        pause.textContent = "Resume";
        status.textContent = "Paused";
      }
    });
    stop.addEventListener("click", () => {
      if (activePlayback?.controls === controls) stopActivePlayback();
    });
    return controls;
  }

  async function sendMessage({ autoSpeak = false } = {}) {
    const text = $input.value.trim();
    if (!text || isStreaming) return;

    addMessage("user", text);
    $input.value = "";
    $input.style.height = "auto";
    isStreaming = true;
    updateButtons();
    addTypingIndicator();

    try {
      const response = await fetch(`${API}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
        body: JSON.stringify({ messages: [{ role: "user", content: text }], stream: true }),
      });
      removeTypingIndicator();
      if (!response.ok) {
        addMessage("assistant", `⚠️ Error: ${await response.text()}`);
        return;
      }

      const bubble = addMessage("assistant", "");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";
      let streamError = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }
          if (event.type === "error") {
            streamError = true;
            fullText += `\n⚠️ ${event.message}`;
          } else if (event.type === "delta") fullText += event.text;
          else continue;
          bubble.innerHTML = renderMarkdown(fullText);
          scrollToBottom();
        }
      }
      buffer += decoder.decode();
      if (!fullText) {
        bubble.innerHTML = '<span style="color:var(--text-tertiary)">No response received.</span>';
      } else if (!streamError) {
        const controls = addSpeechControls(bubble, fullText);
        if (autoSpeak) await playSpeech(fullText, controls);
      }
    } catch (error) {
      removeTypingIndicator();
      addMessage("assistant", `⚠️ Network error: ${error.message}`);
    } finally {
      isStreaming = false;
      updateButtons();
    }
  }

  async function stopMicrophoneTracks() {
    if (microphoneStream) {
      microphoneStream.getTracks().forEach((track) => track.stop());
      microphoneStream = null;
    }
  }

  function audioExtension(mimeType) {
    if (mimeType.includes("webm")) return "webm";
    if (mimeType.includes("ogg")) return "ogg";
    if (mimeType.includes("mp4")) return "mp4";
    return "webm";
  }

  async function finishRecording() {
    await stopMicrophoneTracks();
    $voiceBtn.classList.remove("recording");
    $voiceBtn.title = "Start voice chat";
    $voiceBtn.setAttribute("aria-label", "Start voice chat");
    const mimeType = recorder?.mimeType || recordedChunks[0]?.type || "audio/webm";
    const audioBlob = new Blob(recordedChunks, { type: mimeType });
    recordedChunks = [];
    recorder = null;

    if (!audioBlob.size) {
      $voiceStatus.textContent = "No audio captured. Try again.";
      voiceBusy = false;
      updateButtons();
      return;
    }
    if (audioBlob.size > 25 * 1024 * 1024) {
      $voiceStatus.textContent = "Recording is over the 25 MB limit.";
      voiceBusy = false;
      updateButtons();
      return;
    }

    $voiceStatus.textContent = "Transcribing your voice…";
    const form = new FormData();
    form.append("file", audioBlob, `recording.${audioExtension(mimeType)}`);
    try {
      const response = await fetch(`${API}/api/voice/transcribe`, { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Transcription failed.");
      const transcript = result.text.trim();
      if (!transcript) {
        $voiceStatus.textContent = "I didn't catch that. Tap the microphone and try again.";
        return;
      }
      $input.value = transcript;
      $input.style.height = "auto";
      $input.style.height = Math.min($input.scrollHeight, 150) + "px";
      $voiceStatus.textContent = "Sending your request…";
      voiceBusy = false;
      updateButtons();
      await sendMessage({ autoSpeak: true });
      $voiceStatus.textContent = "Voice turn complete. Tap the microphone to speak again.";
    } catch (error) {
      $voiceStatus.textContent = `Voice error: ${error.message}`;
    } finally {
      voiceBusy = false;
      updateButtons();
    }
  }

  async function toggleRecording() {
    if (recorder?.state === "recording") {
      voiceBusy = true;
      $voiceStatus.textContent = "Finishing recording…";
      recorder.stop();
      updateButtons();
      return;
    }
    if (isStreaming || voiceBusy) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      $voiceStatus.textContent = "This browser does not support microphone recording.";
      return;
    }
    try {
      microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeTypes = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
      const mimeType = mimeTypes.find((type) => MediaRecorder.isTypeSupported(type));
      recorder = mimeType ? new MediaRecorder(microphoneStream, { mimeType }) : new MediaRecorder(microphoneStream);
      recordedChunks = [];
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size) recordedChunks.push(event.data);
      });
      recorder.addEventListener("stop", finishRecording, { once: true });
      recorder.start();
      $voiceBtn.classList.add("recording");
      $voiceBtn.title = "Stop recording and send";
      $voiceBtn.setAttribute("aria-label", "Stop recording and send");
      $voiceStatus.textContent = "Listening… tap the microphone again when you're done.";
      updateButtons();
    } catch (error) {
      await stopMicrophoneTracks();
      recorder = null;
      $voiceBtn.classList.remove("recording");
      $voiceStatus.textContent = `Microphone error: ${error.message}`;
      updateButtons();
    }
  }

  $input.addEventListener("input", () => {
    $input.style.height = "auto";
    $input.style.height = `${Math.min($input.scrollHeight, 150)}px`;
    updateButtons();
  });
  $input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  $sendBtn.addEventListener("click", () => sendMessage());
  $voiceBtn.addEventListener("click", toggleRecording);

  function bindQuickActions() {
    document.querySelectorAll(".quick-btn").forEach((button) => {
      button.addEventListener("click", () => {
        $input.value = button.dataset.prompt;
        updateButtons();
        sendMessage();
      });
    });
  }
  bindQuickActions();

  $newChat.addEventListener("click", () => {
    stopActivePlayback();
    if (recorder?.state === "recording") recorder.stop();
    sessionId = crypto.randomUUID();
    $messages.innerHTML = `
      <div class="welcome">
        <div class="welcome-icon">💎</div>
        <h2>Hey, I'm Ruby</h2>
        <p>Your personal AI assistant. Ask me anything.</p>
        <div class="quick-actions">
          <button class="quick-btn" data-prompt="Explain quantum computing in simple terms">✨ Explain quantum computing</button>
          <button class="quick-btn" data-prompt="Write a Python function to reverse a linked list">🐍 Python linked list</button>
          <button class="quick-btn" data-prompt="What are the best practices for REST API design?">🌐 REST API best practices</button>
        </div>
      </div>`;
    $voiceStatus.textContent = "Tap the microphone to speak";
    bindQuickActions();
    $input.focus();
  });

  updateButtons();
})();
