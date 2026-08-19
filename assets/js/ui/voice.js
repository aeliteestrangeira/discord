import { emit } from "./runtime.js";
import { VOICE_CAPTURE } from "./voice-capture.js";
import { trustedElement } from "./dom.js";
import { voiceControlSoundboard } from "./voice-sounds.js";

const POLL_MS = 1000;
const PING_MS = 3000;
const FALLBACK_AVATAR = "/images/0208-2ccd8ae8b2379360.png";
let activeVoiceRuntime = null;

function readGuildBootstrap() {
  const node = document.getElementById("app-guild-bootstrap");
  if (!node) return null;
  try {
    const value = JSON.parse(node.textContent || "{}");
    return value?.id ? value : null;
  } catch (_) {
    return null;
  }
}

function voiceChannelFromGuild(guild) {
  const channels = Array.isArray(guild?.channels) ? guild.channels : [];
  return channels.find((item) => String(item?.type || "").toLowerCase() === "voice") || null;
}

function voiceAnchor() {
  return document.querySelector('a[aria-label*="canal de voz" i], a[data-list-item-id][aria-label*="voice channel" i]');
}

function voicePanels() {
  return document.querySelector("section.panels__5e434");
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds || 0));
  const minutes = Math.floor(seconds / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function titleCaseChannel(name) {
  const clean = String(name || "General").trim() || "General";
  return clean.charAt(0).toUpperCase() + clean.slice(1);
}

function capturedNode(markup) {
  return trustedElement(String(markup || "").trim());
}

function cleanText(value, fallback = "") {
  const text = String(value ?? fallback).trim();
  return text || fallback;
}

function muteButton() {
  return voicePanels()?.querySelector('.buttons__37e49 button[role="switch"][aria-label="Silenciar"], .buttons__37e49 button[role="switch"][aria-label="Mute"]') || null;
}

function deafenButton() {
  return voicePanels()?.querySelector('.buttons__37e49 button[role="switch"][aria-label="Desativar áudio"], .buttons__37e49 button[role="switch"][aria-label="Deafen"]') || null;
}

function emptyIntroLayer() {
  const layers = [...document.querySelectorAll(".layerContainer__59d0d")];
  return layers.find((item) => item.childElementCount === 0) || null;
}

class VoiceRuntime {
  constructor(authProvider, user, guild) {
    this.auth = authProvider;
    this.user = user || {};
    this.guild = guild;
    this.voiceChannel = voiceChannelFromGuild(guild);
    this.anchor = voiceAnchor();
    this.localStream = null;
    this.voiceSessionId = "";
    this.iceServers = [];
    this.participants = [];
    this.peers = new Map();
    this.remoteAudio = new Map();
    this.pollTimer = null;
    this.durationTimer = null;
    this.pingTimer = null;
    this.joinedAt = 0;
    this.polling = false;
    this.joining = false;
    this.muted = true;
    this.deafened = false;
    this.noiseSuppression = true;
    this.originalAccountSubtext = null;
    this.originalMuteIcon = null;
    this.voiceUsersList = null;
    this.durationNode = null;
    this.pingLabel = null;
    this.introHost = null;
    this.introPopup = null;
    this.introResizeHandler = null;
    this.pagehideHandler = () => this.leave({ silent: true });
    this.controlEventHandler = (event) => this.applyControlAction(event?.detail?.action);
  }

  wire() {
    if (!this.voiceChannel || !this.anchor || !navigator.mediaDevices?.getUserMedia || typeof RTCPeerConnection === "undefined") return;
    const panels = voicePanels();
    const accountSubtext = panels?.querySelector(".panelSubtextContainer__37e49 .subtext__339d0");
    const micIcon = muteButton()?.querySelector(".lottieIcon__5eb9b");
    this.originalAccountSubtext = accountSubtext?.cloneNode(true) || null;
    this.originalMuteIcon = micIcon?.cloneNode(true) || null;
    this.anchor.dataset.appVoiceChannelId = String(this.voiceChannel.id || "");
    const activate = (event) => {
      event?.preventDefault();
      event?.stopPropagation();
      if (!this.voiceSessionId) this.join();
    };
    this.anchor.addEventListener("click", activate);
    this.anchor.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") activate(event);
    });
    window.addEventListener("pagehide", this.pagehideHandler, { capture: true });
    window.addEventListener("app:voice-control", this.controlEventHandler);
  }

  async join() {
    if (this.joining || this.voiceSessionId) return;
    this.joining = true;
    emit("app:voice-permission-requested", { guildId: this.guild.id, channelId: this.voiceChannel.id });
    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: false,
      });
      const result = await this.auth.joinVoice(this.guild.id, this.voiceChannel.id);
      if (result?.error || !result?.data?.sessionId) throw new Error(result?.error?.message || "voice_join_failed");
      this.localStream = stream;
      this.voiceSessionId = String(result.data.sessionId);
      this.iceServers = Array.isArray(result.data.iceServers) ? result.data.iceServers : [];
      this.joinedAt = Date.now();
      this.muted = false;
      this.deafened = false;
      this.noiseSuppression = true;
      voiceControlSoundboard.prepare();
      this.renderConnected(result.data);
      this.applyParticipants(result.data.participants || []);
      await this.ensurePeers();
      this.pollTimer = window.setInterval(() => this.sync(), POLL_MS);
      this.pingTimer = window.setInterval(() => this.updatePing(), PING_MS);
      this.durationTimer = window.setInterval(() => this.updateDuration(), 1000);
      this.updateDuration();
      this.showIntroOnce();
      emit("app:voice-connected", { guildId: this.guild.id, channelId: this.voiceChannel.id });
    } catch (error) {
      if (this.voiceSessionId || this.localStream) {
        try { await this.leave({ silent: true }); } catch (_) {}
      } else {
        stream?.getTracks().forEach((track) => track.stop());
      }
      emit("app:voice-connect-failed", { name: error?.name || "voice_error" });
      if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
        console.warn("Permissão de microfone negada pelo navegador.");
      } else {
        console.error("Falha ao conectar ao canal de voz.", error);
      }
    } finally {
      this.joining = false;
    }
  }

  renderConnected(data) {
    this.renderVoiceUsers(data.participants || []);
    this.setSelectedChannel(true);
    this.renderVoicePanel(titleCaseChannel(data.channelName || this.voiceChannel.name), data.guildName || this.guild.name);
    this.setAccountVoiceState(true);
    this.syncAudioControls();
  }

  setSelectedChannel(selected) {
    const wrapper = this.anchor?.closest(".wrapper__2ea32");
    const children = this.anchor?.querySelector(".children__2ea32");
    if (!wrapper || !children) return;

    wrapper.classList.toggle("selectedChannel_c69b6d", selected);
    wrapper.classList.toggle("modeSelected__2ea32", selected);
    if (selected) this.anchor.setAttribute("aria-current", "page");
    else this.anchor.removeAttribute("aria-current");
    this.anchor.querySelector("svg.icon__2ea32")?.classList.toggle("iconLive_c69b6d", selected);

    for (const icon of this.anchor.querySelectorAll(".iconBase_c69b6d")) {
      icon.classList.toggle("iconNoChannelInfo_c69b6d", !selected);
      icon.classList.toggle("iconWithChannelInfo_c69b6d", selected);
    }

    if (selected && !this.durationNode) {
      const captured = capturedNode(VOICE_CAPTURE.channelInfo);
      if (captured) {
        this.durationNode = captured;
        const hidden = captured.querySelector('span[role="timer"]');
        const visible = captured.querySelector('span[aria-hidden="true"]');
        if (hidden) hidden.textContent = "0 seconds";
        if (visible) visible.textContent = "0:00";
        children.appendChild(captured);
      }
    }
    if (!selected && this.durationNode) {
      this.durationNode.remove();
      this.durationNode = null;
    }
  }

  updateDuration() {
    if (!this.voiceSessionId) return;
    const elapsed = Math.max(0, Math.floor((Date.now() - this.joinedAt) / 1000));
    const text = formatDuration(elapsed);
    const hidden = this.durationNode?.querySelector('span[role="timer"]');
    const visible = this.durationNode?.querySelector('span[aria-hidden="true"]');
    if (hidden) {
      const minutes = Math.floor(elapsed / 60);
      const seconds = elapsed % 60;
      hidden.textContent = `${minutes ? `${minutes} minute${minutes === 1 ? "" : "s"}, ` : ""}${seconds} second${seconds === 1 ? "" : "s"}`;
    }
    if (visible) visible.textContent = text;
    const name = titleCaseChannel(this.voiceChannel?.name || "General");
    const username = cleanText(this.user?.username, "user");
    this.anchor?.setAttribute("aria-label", `${name} (voice channel), ${username}, call duration ${text}`);
  }

  renderVoiceUsers(participants) {
    const li = this.anchor?.closest("li.containerDefault_c69b6d");
    if (!li) return;
    if (!this.voiceUsersList) {
      this.voiceUsersList = capturedNode(VOICE_CAPTURE.voiceUsersList);
      if (!this.voiceUsersList) return;
      li.appendChild(this.voiceUsersList);
    }

    const capturedItem = capturedNode(VOICE_CAPTURE.voiceUsersList)?.querySelector(".draggable__55bab");
    if (!capturedItem) return;
    const fragment = document.createDocumentFragment();
    for (const participant of participants) {
      const item = capturedItem.cloneNode(true);
      const username = cleanText(participant?.username, "user");
      item.setAttribute("data-dnd-name", titleCaseChannel(this.voiceChannel?.name || "General"));
      item.querySelector(".focusTarget__54e4b")?.setAttribute("aria-label", username);
      const usernameNode = item.querySelector(".username__07f91");
      if (usernameNode) usernameNode.textContent = username;
      const avatar = item.querySelector(".userAvatar__55bab");
      if (avatar) avatar.style.backgroundImage = `url("${FALLBACK_AVATAR}")`;
      fragment.appendChild(item);
    }
    this.voiceUsersList.replaceChildren(fragment);
  }

  renderVoicePanel(channelName, guildName) {
    const target = voicePanels()?.querySelector(".wrapper_e131a9");
    const captured = capturedNode(VOICE_CAPTURE.connectedWrapper);
    if (!target || !captured) return;
    target.replaceChildren(...[...captured.childNodes].map((node) => node.cloneNode(true)));

    const channel = cleanText(channelName, "General");
    const guild = cleanText(guildName, "Server");
    const route = target.querySelector("a[href^=\"/channels/\"]");
    if (route) route.setAttribute("href", `/channels/${encodeURIComponent(String(this.guild.id))}/${encodeURIComponent(String(this.voiceChannel.id))}`);
    const channelLabel = target.querySelector(".channel_e131a9 .lineClamp1__4bd52");
    if (channelLabel) channelLabel.textContent = `${channel} / ${guild}`;

    this.pingLabel = target.querySelector(".rtcConnectionStatusWrapper__06d62 span.hiddenVisually_b18fe2");
    if (this.pingLabel) this.pingLabel.textContent = "— ms";
    target.querySelector('button[aria-label="Disconnect"]')?.addEventListener("click", () => this.leave());
    target.querySelector('button[aria-label="Noise Suppression powered by Krisp"]')?.addEventListener("click", () => this.toggleNoiseSuppression());
  }

  setAccountVoiceState(active) {
    const panels = voicePanels();
    const current = panels?.querySelector(".panelSubtextContainer__37e49 .subtext__339d0");
    if (!current) return;
    if (active) {
      const captured = capturedNode(VOICE_CAPTURE.accountSubtext);
      if (!captured) return;
      const username = cleanText(this.user?.username, "user");
      const hovered = captured.querySelector(".hovered__0263c");
      if (hovered) hovered.textContent = username;
      const status = captured.querySelector(".activityStatusText__37e49");
      if (status) status.textContent = "In voice";
      current.replaceWith(captured);
    } else if (this.originalAccountSubtext) {
      current.replaceWith(this.originalAccountSubtext.cloneNode(true));
    }
  }

  syncAudioControls() {
    const mute = muteButton();
    const deafen = deafenButton();
    if (mute) {
      mute.setAttribute("aria-checked", this.muted ? "true" : "false");
      mute.classList.toggle("redGlow__67645", this.muted);
      const parent = mute.closest(".audioButtonParent__5e764");
      parent?.classList.toggle("hasColorGlow__5e764", this.muted);
      parent?.querySelector(".buttonChevron__5e764")?.classList.toggle("redGlow__67645", this.muted);

      const holder = mute.querySelector(".lottieIcon__5eb9b");
      const desired = this.muted ? this.originalMuteIcon?.cloneNode(true) : capturedNode(VOICE_CAPTURE.unmutedMicIcon);
      if (holder && desired) holder.replaceWith(desired);
      if (!mute.dataset.appVoiceWired) {
        mute.dataset.appVoiceWired = "true";
        mute.addEventListener("click", () => this.toggleMute());
      }
    }
    if (deafen) {
      deafen.setAttribute("aria-checked", this.deafened ? "true" : "false");
      deafen.classList.toggle("redGlow__67645", this.deafened);
      const parent = deafen.closest(".audioButtonParent__5e764");
      parent?.classList.toggle("hasColorGlow__5e764", this.deafened);
      parent?.querySelector(".buttonChevron__5e764")?.classList.toggle("redGlow__67645", this.deafened);
      if (!deafen.dataset.appVoiceWired) {
        deafen.dataset.appVoiceWired = "true";
        deafen.addEventListener("click", () => this.toggleDeafen());
      }
    }
  }

  setMicrophoneMuted(muted, { sound = true } = {}) {
    if (!this.localStream) return false;
    const desired = Boolean(muted);
    if (this.muted === desired) return true;
    this.muted = desired;
    for (const track of this.localStream.getAudioTracks()) track.enabled = !this.muted;
    if (sound) voiceControlSoundboard.microphone(this.muted);
    this.syncAudioControls();
    emit("app:voice-mute-changed", { muted: this.muted });
    return true;
  }

  setHeadphonesMuted(muted, { sound = true } = {}) {
    if (!this.voiceSessionId) return false;
    const desired = Boolean(muted);
    if (this.deafened === desired) return true;
    this.deafened = desired;
    for (const audio of this.remoteAudio.values()) audio.muted = this.deafened;
    if (sound) voiceControlSoundboard.headphone(this.deafened);
    this.syncAudioControls();
    emit("app:voice-deafen-changed", { deafened: this.deafened });
    return true;
  }

  toggleMute() {
    this.setMicrophoneMuted(!this.muted);
  }

  toggleDeafen() {
    this.setHeadphonesMuted(!this.deafened);
  }

  applyControlAction(action) {
    switch (String(action || "").toLowerCase()) {
      case "mute-microphone": return this.setMicrophoneMuted(true);
      case "unmute-microphone": return this.setMicrophoneMuted(false);
      case "toggle-microphone": return this.setMicrophoneMuted(!this.muted);
      case "mute-headphone": return this.setHeadphonesMuted(true);
      case "unmute-headphone": return this.setHeadphonesMuted(false);
      case "toggle-headphone": return this.setHeadphonesMuted(!this.deafened);
      default: return false;
    }
  }

  async toggleNoiseSuppression() {
    const track = this.localStream?.getAudioTracks?.()[0];
    if (!track?.applyConstraints) return;
    const desired = !this.noiseSuppression;
    try {
      await track.applyConstraints({ noiseSuppression: desired });
      this.noiseSuppression = desired;
      const button = voicePanels()?.querySelector('button[aria-label="Noise Suppression powered by Krisp"]');
      button?.setAttribute("aria-pressed", desired ? "true" : "false");
    } catch (_) {}
  }

  async createPeer(remoteSessionId) {
    if (!this.localStream || !remoteSessionId || remoteSessionId === this.voiceSessionId) return null;
    if (this.peers.has(remoteSessionId)) return this.peers.get(remoteSessionId);
    const pc = new RTCPeerConnection({ iceServers: this.iceServers });
    const entry = { pc, remoteSessionId, offerStarted: false, pendingIce: [] };
    this.peers.set(remoteSessionId, entry);
    for (const track of this.localStream.getTracks()) pc.addTrack(track, this.localStream);
    pc.addEventListener("icecandidate", (event) => {
      if (!event.candidate || !this.voiceSessionId) return;
      this.sendSignal(remoteSessionId, "ice", event.candidate.toJSON()).catch(() => {});
    });
    pc.addEventListener("track", (event) => {
      let audio = this.remoteAudio.get(remoteSessionId);
      if (!audio) {
        audio = document.createElement("audio");
        audio.autoplay = true;
        audio.playsInline = true;
        audio.hidden = true;
        audio.muted = this.deafened;
        audio.dataset.appVoiceRemoteSession = remoteSessionId;
        document.body.appendChild(audio);
        this.remoteAudio.set(remoteSessionId, audio);
      }
      audio.srcObject = event.streams?.[0] || new MediaStream([event.track]);
      audio.play().catch(() => {});
    });
    pc.addEventListener("connectionstatechange", () => {
      if (["failed", "closed"].includes(pc.connectionState)) this.closePeer(remoteSessionId);
    });
    return entry;
  }

  async ensurePeers() {
    for (const participant of this.participants) {
      const remote = String(participant?.sessionId || "");
      if (!remote || remote === this.voiceSessionId) continue;
      const entry = await this.createPeer(remote);
      if (!entry || entry.offerStarted) continue;
      if (this.voiceSessionId.localeCompare(remote) < 0) {
        entry.offerStarted = true;
        try {
          const offer = await entry.pc.createOffer({ offerToReceiveAudio: true });
          await entry.pc.setLocalDescription(offer);
          await this.sendSignal(remote, "offer", entry.pc.localDescription.toJSON());
        } catch (error) {
          entry.offerStarted = false;
          console.warn("Falha na oferta WebRTC.", error);
        }
      }
    }
    const active = new Set(this.participants.map((p) => String(p?.sessionId || "")));
    for (const remote of [...this.peers.keys()]) {
      if (!active.has(remote)) this.closePeer(remote);
    }
  }

  async sendSignal(targetSessionId, type, payload) {
    if (!this.voiceSessionId) return;
    const result = await this.auth.sendVoiceSignal(this.voiceSessionId, targetSessionId, type, payload);
    if (result?.error && result.status !== 409) throw new Error(result.error.message || "voice_signal_error");
  }

  async handleSignal(signal) {
    const remote = String(signal?.senderSessionId || "");
    if (!remote || remote === this.voiceSessionId) return;
    const entry = await this.createPeer(remote);
    if (!entry) return;
    const pc = entry.pc;
    if (signal.type === "offer") {
      await pc.setRemoteDescription(new RTCSessionDescription(signal.payload));
      for (const candidate of entry.pendingIce.splice(0)) await pc.addIceCandidate(candidate).catch(() => {});
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await this.sendSignal(remote, "answer", pc.localDescription.toJSON());
      return;
    }
    if (signal.type === "answer") {
      if (pc.signalingState === "have-local-offer") {
        await pc.setRemoteDescription(new RTCSessionDescription(signal.payload));
        for (const candidate of entry.pendingIce.splice(0)) await pc.addIceCandidate(candidate).catch(() => {});
      }
      return;
    }
    if (signal.type === "ice") {
      const candidate = new RTCIceCandidate(signal.payload);
      if (pc.remoteDescription) await pc.addIceCandidate(candidate).catch(() => {});
      else entry.pendingIce.push(candidate);
    }
  }

  async sync() {
    if (!this.voiceSessionId || this.polling) return;
    this.polling = true;
    try {
      const result = await this.auth.voiceState(this.voiceSessionId);
      if (result?.error) {
        if (result.status === 410) await this.leave({ silent: true });
        return;
      }
      const data = result.data || {};
      for (const signal of data.signals || []) {
        try { await this.handleSignal(signal); } catch (error) { console.warn("Sinal WebRTC ignorado.", error); }
      }
      this.applyParticipants(data.participants || []);
      await this.ensurePeers();
    } finally {
      this.polling = false;
    }
  }

  applyParticipants(participants) {
    this.participants = Array.isArray(participants) ? participants : [];
    this.renderVoiceUsers(this.participants);
  }

  async updatePing() {
    const values = [];
    for (const { pc } of this.peers.values()) {
      if (pc.connectionState !== "connected") continue;
      try {
        const stats = await pc.getStats();
        stats.forEach((report) => {
          if (report.type === "candidate-pair" && report.state === "succeeded" && typeof report.currentRoundTripTime === "number") {
            values.push(report.currentRoundTripTime * 1000);
          }
        });
      } catch (_) {}
    }
    if (!this.pingLabel) return;
    this.pingLabel.textContent = values.length ? `${Math.round(values.reduce((a, b) => a + b, 0) / values.length)} ms` : "— ms";
  }

  closePeer(remoteSessionId) {
    const entry = this.peers.get(remoteSessionId);
    try { entry?.pc?.close(); } catch (_) {}
    this.peers.delete(remoteSessionId);
    const audio = this.remoteAudio.get(remoteSessionId);
    if (audio) {
      try { audio.srcObject = null; } catch (_) {}
      audio.remove();
    }
    this.remoteAudio.delete(remoteSessionId);
  }

  showIntroOnce() {
    const userId = String(this.user?.id || "unknown");
    const key = `app:voice-tip:${userId}:first-voice`;
    try { if (localStorage.getItem(key) === "1") return; } catch (_) {}
    const host = emptyIntroLayer();
    const captured = capturedNode(VOICE_CAPTURE.introLayer);
    const content = captured?.firstElementChild?.cloneNode(true) || null;
    if (!host || !content) return;
    host.replaceChildren(content);
    this.introHost = host;
    this.introPopup = host.querySelector("#popout_1208");

    const position = () => {
      const panels = voicePanels()?.getBoundingClientRect();
      if (!this.introPopup || !panels) return;
      this.introPopup.style.left = `${Math.max(8, Math.round(panels.left + 31))}px`;
      this.introPopup.style.bottom = `${Math.max(8, Math.round(window.innerHeight - panels.top + 8))}px`;
    };
    position();
    this.introResizeHandler = position;
    window.addEventListener("resize", position, { passive: true });
    host.querySelector(".voicePanelIntroductionWrapper_e131a9 button")?.addEventListener("click", () => {
      try { localStorage.setItem(key, "1"); } catch (_) {}
      this.closeIntro();
    }, { once: true });
  }

  closeIntro() {
    this.introHost?.replaceChildren();
    if (this.introResizeHandler) window.removeEventListener("resize", this.introResizeHandler);
    this.introHost = null;
    this.introPopup = null;
    this.introResizeHandler = null;
  }

  async destroy() {
    window.removeEventListener("pagehide", this.pagehideHandler, { capture: true });
    window.removeEventListener("app:voice-control", this.controlEventHandler);
    await this.leave({ silent: true });
  }

  async leave({ silent = false } = {}) {
    const sid = this.voiceSessionId;
    if (!sid && !this.localStream) return;
    this.voiceSessionId = "";
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.durationTimer) clearInterval(this.durationTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pollTimer = this.durationTimer = this.pingTimer = null;
    this.closeIntro();
    for (const remote of [...this.peers.keys()]) this.closePeer(remote);
    this.localStream?.getTracks().forEach((track) => track.stop());
    this.localStream = null;
    this.participants = [];
    this.muted = true;
    this.deafened = false;
    const panels = voicePanels();
    panels?.querySelector(".wrapper_e131a9")?.replaceChildren();
    this.pingLabel = null;
    this.setAccountVoiceState(false);
    this.voiceUsersList?.remove();
    this.voiceUsersList = null;
    this.setSelectedChannel(false);
    this.syncAudioControls();
    if (sid) Promise.resolve(this.auth.leaveVoice(sid)).catch(() => {});
    if (!silent) emit("app:voice-disconnected", { guildId: this.guild.id, channelId: this.voiceChannel.id });
  }
}

export function wireVoiceChannels(authProvider, user) {
  const guild = readGuildBootstrap();
  if (!guild) {
    activeVoiceRuntime?.destroy?.();
    activeVoiceRuntime = null;
    return null;
  }
  activeVoiceRuntime?.destroy?.();
  const runtime = new VoiceRuntime(authProvider, user, guild);
  runtime.wire();
  activeVoiceRuntime = runtime;
  return runtime;
}

export function rewireVoiceChannels(authProvider, user) {
  return wireVoiceChannels(authProvider, user);
}
