export const VOICE_CONTROL_SOUNDS = Object.freeze({
  headphoneMuted: "https://res.cloudinary.com/do7vwsnpg/video/upload/v1787112682/529ff198eac567af_nhesmn.mp3",
  headphoneUnmuted: "https://res.cloudinary.com/do7vwsnpg/video/upload/v1787112724/b150f03c89944403_qvpaen.mp3",
  microphoneMuted: "https://res.cloudinary.com/do7vwsnpg/video/upload/v1787112767/2d3b4ba32c34c862_ooopar.mp3",
  microphoneUnmuted: "https://res.cloudinary.com/do7vwsnpg/video/upload/v1787112805/e74c4a06134a20e4_kzqukf.mp3",
});

class VoiceControlSoundboard {
  constructor() {
    this.players = new Map();
  }

  prepare() {
    if (typeof Audio === "undefined" || this.players.size) return;
    for (const [name, url] of Object.entries(VOICE_CONTROL_SOUNDS)) {
      const audio = new Audio();
      audio.preload = "auto";
      audio.src = url;
      audio.volume = 1;
      this.players.set(name, audio);
      try { audio.load(); } catch (_) {}
    }
  }

  play(name) {
    this.prepare();
    const audio = this.players.get(name);
    if (!audio) return;
    try {
      audio.pause();
      audio.currentTime = 0;
      const playback = audio.play();
      if (playback?.catch) playback.catch(() => {});
    } catch (_) {}
  }

  microphone(muted) {
    this.play(muted ? "microphoneMuted" : "microphoneUnmuted");
  }

  headphone(muted) {
    this.play(muted ? "headphoneMuted" : "headphoneUnmuted");
  }
}

export const voiceControlSoundboard = new VoiceControlSoundboard();
