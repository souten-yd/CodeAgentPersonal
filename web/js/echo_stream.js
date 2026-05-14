(function () {
  "use strict";

  const root = window;
  const registry = root.__kasaneModules || (root.__kasaneModules = {});
  const state = {
    recording: false,
    stoppingOrSaving: false,
    connectionState: "disconnected",
    mediaRecorder: null,
    mediaStream: null,
    websocket: null,
    playbackState: "idle",
    lastError: "",
  };

  function getState() {
    return Object.assign({}, state);
  }

  function setRecording(value) {
    state.recording = !!value;
    return state.recording;
  }

  function setStoppingOrSaving(value) {
    state.stoppingOrSaving = !!value;
    return state.stoppingOrSaving;
  }

  function setConnectionState(value) {
    state.connectionState = value || "disconnected";
    return state.connectionState;
  }

  function setPlaybackState(value) {
    state.playbackState = value || "idle";
    return state.playbackState;
  }

  function setMediaRecorder(recorder) {
    state.mediaRecorder = recorder || null;
    return state.mediaRecorder;
  }

  function setMediaStream(stream) {
    state.mediaStream = stream || null;
    return state.mediaStream;
  }

  function setWebSocket(socket) {
    state.websocket = socket || null;
    return state.websocket;
  }

  function setLastError(error) {
    state.lastError = error ? String(error.message || error) : "";
    return state.lastError;
  }

  const api = {
    name: "echo_stream",
    loaded: true,
    getState,
    setRecording,
    setStoppingOrSaving,
    setConnectionState,
    setPlaybackState,
    setMediaRecorder,
    setMediaStream,
    setWebSocket,
    setLastError,
  };

  registry.echoStream = Object.assign(registry.echoStream || {}, api);
  root.EchoStream = Object.assign(root.EchoStream || {}, api);
}());
