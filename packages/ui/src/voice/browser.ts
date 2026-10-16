import type { VoiceSpeechPort } from "./types.js";
import type { TrackingVoiceController } from "./controller.js";

/** Constructing/detecting this port never speaks. Only localService=true voices can be selected. */
export function createWebSpeechPort(target: (Window & typeof globalThis) | undefined = typeof window === "undefined" ? undefined : window): VoiceSpeechPort {
  let owned: SpeechSynthesisUtterance | undefined;
  const supported = () => !!target && !!target.speechSynthesis && typeof target.SpeechSynthesisUtterance === "function";
  const localVoice = () => {
    if (!supported()) return undefined;
    const voices = target!.speechSynthesis.getVoices().filter(voice => voice.localService === true);
    return voices.find(voice => /^zh[-_]/i.test(voice.lang)) ?? voices.find(voice => voice.default) ?? voices[0];
  };
  const cancel = () => {
    const utterance = owned; owned = undefined;
    if (utterance) { utterance.onstart = null; utterance.onend = null; utterance.onerror = null; target!.speechSynthesis.cancel(); }
  };
  return {
    availability() { try { return !supported() ? "unsupported" : localVoice() ? "available" : "no-local-voice"; } catch { return "unsupported"; } },
    isUserGesture(event) {
      return supported() && event.isTrusted === true && ["click", "keydown", "pointerup", "touchend"].includes(event.type) && target!.navigator.userActivation?.isActive !== false;
    },
    speak(text, hooks) {
      const voice = localVoice(); if (!voice) { hooks.error(); return; }
      cancel(); const utterance = new target!.SpeechSynthesisUtterance(text); owned = utterance;
      utterance.voice = voice; utterance.lang = voice.lang; utterance.rate = 1.1; utterance.pitch = 1; utterance.volume = 1;
      utterance.onstart = () => { if (owned === utterance) hooks.start(); };
      utterance.onend = () => { if (owned === utterance) { owned = undefined; hooks.end(); } };
      utterance.onerror = () => { if (owned === utterance) { owned = undefined; hooks.error(); } };
      try { target!.speechSynthesis.speak(utterance); } catch { cancel(); hooks.error(); }
    },
    cancel,
    observe(listener) {
      if (!supported()) return () => {};
      target!.speechSynthesis.addEventListener("voiceschanged", listener);
      return () => target!.speechSynthesis.removeEventListener("voiceschanged", listener);
    },
  };
}

/** Host must additionally forward B1 revocation/session changes and the existing EventSource's open/error/close. */
export function bindVoiceBrowserLifecycle(controller: TrackingVoiceController, target: Window | undefined = typeof window === "undefined" ? undefined : window): () => void {
  if (!target) return () => controller.destroy();
  const stop = () => controller.suspend();
  const check = () => controller.tick();
  const storage = (event: StorageEvent) => { if (event.key === null || event.key === controller.preferenceKey()) controller.reloadPreferences(); };
  target.addEventListener("pagehide", stop); target.document.addEventListener("freeze", stop);
  target.document.addEventListener("visibilitychange", check); target.addEventListener("storage", storage);
  return () => {
    target.removeEventListener("pagehide", stop); target.document.removeEventListener("freeze", stop);
    target.document.removeEventListener("visibilitychange", check); target.removeEventListener("storage", storage); controller.destroy();
  };
}
