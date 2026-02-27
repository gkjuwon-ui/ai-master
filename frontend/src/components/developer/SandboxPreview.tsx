'use client';

import { useRef, useState, useCallback, useEffect } from 'react';
import {
  Monitor, Maximize2, Minimize2, RotateCcw, ExternalLink,
  MousePointer, Loader2, AlertTriangle, Shield, Play,
  Square, Settings2, FolderOpen, RefreshCw, Wifi, WifiOff
} from 'lucide-react';
import { useIDEStore } from '@/store/ideStore';

// Access Electron API
function getElectronAPI(): any {
  if (typeof window !== 'undefined' && (window as any).electronAPI) {
    return (window as any).electronAPI;
  }
  return null;
}

export default function SandboxPreview() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const thumbnailIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const [thumbnailSrc, setThumbnailSrc] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [memoryMB, setMemoryMB] = useState(4096);
  const [showConfig, setShowConfig] = useState(false);

  const {
    sandboxRunning,
    setSandboxRunning,
    sandboxAvailable,
    setSandboxAvailable,
    sandboxLaunching,
    setSandboxLaunching,
    isRecording,
    addTerminalLog,
  } = useIDEStore();

  const api = getElectronAPI();

  // Check if Windows Sandbox is available
  useEffect(() => {
    async function check() {
      if (!api?.sandbox) {
        setSandboxAvailable(false);
        return;
      }
      try {
        const available = await api.sandbox.checkAvailable();
        setSandboxAvailable(available);
      } catch {
        setSandboxAvailable(false);
      }
    }
    check();
  }, [api, setSandboxAvailable]);

  // Poll sandbox running state
  useEffect(() => {
    if (!api?.sandbox) return;

    const poll = async () => {
      try {
        const running = await api.sandbox.isRunning();
        setSandboxRunning(running);
      } catch {}
    };
    poll();
    pollIntervalRef.current = setInterval(poll, 3000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [api, setSandboxRunning]);

  // Start periodic thumbnail capture when sandbox is running
  useEffect(() => {
    if (!sandboxRunning || !api?.sandbox || isStreaming) {
      if (thumbnailIntervalRef.current) {
        clearInterval(thumbnailIntervalRef.current);
        thumbnailIntervalRef.current = null;
      }
      if (!sandboxRunning) {
        setThumbnailSrc(null);
      }
      return;
    }

    const capture = async () => {
      try {
        const thumb = await api.sandbox.getThumbnail();
        if (thumb) setThumbnailSrc(thumb);
      } catch {}
    };
    // First capture with a slight delay for sandbox to render
    setTimeout(capture, 1000);
    thumbnailIntervalRef.current = setInterval(capture, 1500);

    return () => {
      if (thumbnailIntervalRef.current) {
        clearInterval(thumbnailIntervalRef.current);
        thumbnailIntervalRef.current = null;
      }
    };
  }, [sandboxRunning, api, isStreaming]);

  // Start live video stream
  const startStream = useCallback(async () => {
    if (!api?.sandbox) return;
    setStreamError(null);

    try {
      // Tell main process we want sandbox capture
      await api.sandbox.requestCapture();

      // Request display media (main process handler will auto-select sandbox window)
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
      });

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setIsStreaming(true);

      // Stop thumbnail capture while streaming
      if (thumbnailIntervalRef.current) {
        clearInterval(thumbnailIntervalRef.current);
        thumbnailIntervalRef.current = null;
      }

      // Handle stream end
      stream.getVideoTracks()[0]?.addEventListener('ended', () => {
        setIsStreaming(false);
        streamRef.current = null;
      });
    } catch (err: any) {
      console.error('Stream error:', err);
      setStreamError(err.message || 'Failed to capture sandbox window');
    }
  }, [api]);

  // Stop stream
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsStreaming(false);
  }, []);

  // Launch sandbox
  const handleLaunch = useCallback(async () => {
    if (!api?.sandbox) return;

    setSandboxLaunching(true);
    addTerminalLog({ type: 'system', message: '🚀 Starting Windows Sandbox...' });

    try {
      const result = await api.sandbox.launch({
        memoryMB,
        mappedFolders: [],
        logonCommand: null,
      });

      if (result.success) {
        addTerminalLog({ type: 'info', message: '  Windows Sandbox is starting up...' });
        addTerminalLog({ type: 'system', message: '  This may take 10-20 seconds on first launch.' });

        // Wait for it to actually start
        let attempts = 0;
        const waitForStart = setInterval(async () => {
          attempts++;
          try {
            const running = await api.sandbox.isRunning();
            if (running) {
              clearInterval(waitForStart);
              setSandboxRunning(true);
              setSandboxLaunching(false);
              addTerminalLog({ type: 'system', message: '✅ Windows Sandbox is running!' });
            } else if (attempts > 40) { // 40 * 1.5s = 60s timeout
              clearInterval(waitForStart);
              setSandboxLaunching(false);
              addTerminalLog({ type: 'error', message: '❌ Sandbox startup timed out.' });
            }
          } catch {
            if (attempts > 40) {
              clearInterval(waitForStart);
              setSandboxLaunching(false);
            }
          }
        }, 1500);
      } else {
        setSandboxLaunching(false);
        addTerminalLog({ type: 'error', message: `❌ Failed to launch sandbox: ${result.error}` });
      }
    } catch (err: any) {
      setSandboxLaunching(false);
      addTerminalLog({ type: 'error', message: `❌ Error: ${err.message}` });
    }
  }, [api, memoryMB, setSandboxRunning, setSandboxLaunching, addTerminalLog]);

  // Stop sandbox
  const handleStop = useCallback(async () => {
    if (!api?.sandbox) return;

    stopStream();
    addTerminalLog({ type: 'system', message: '⏹️ Stopping Windows Sandbox...' });

    try {
      const result = await api.sandbox.stop();
      if (result.success) {
        setSandboxRunning(false);
        setThumbnailSrc(null);
        addTerminalLog({ type: 'system', message: '✅ Sandbox stopped.' });
      } else {
        addTerminalLog({ type: 'warn', message: `Stop warning: ${result.error}` });
        setSandboxRunning(false);
      }
    } catch (err: any) {
      addTerminalLog({ type: 'error', message: `Stop error: ${err.message}` });
    }
  }, [api, stopStream, setSandboxRunning, addTerminalLog]);

  // Focus sandbox window
  const handleFocusSandbox = useCallback(async () => {
    if (!api?.sandbox) return;
    await api.sandbox.focus();
  }, [api]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopStream();
      if (thumbnailIntervalRef.current) clearInterval(thumbnailIntervalRef.current);
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [stopStream]);

  // ─── Not Available State ───
  if (sandboxAvailable === false) {
    return (
      <div className="flex flex-col h-full bg-bg-secondary">
        <div className="flex items-center justify-between px-4 py-2.5 bg-bg-secondary border-b border-border-primary">
          <div className="flex items-center gap-2.5">
            <Monitor size={15} className="text-accent" />
            <span className="text-sm font-medium text-text-primary">Sandbox</span>
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-5 max-w-sm px-8">
            <div className="w-16 h-16 rounded-2xl bg-yellow-500/10 flex items-center justify-center mx-auto">
              <AlertTriangle size={28} className="text-yellow-500" />
            </div>
            <div>
              <p className="text-lg font-semibold text-text-primary">Windows Sandbox Not Available</p>
              <p className="text-sm text-text-tertiary mt-2 leading-relaxed">
                Windows Sandbox is a Windows 10/11 Pro feature. To enable it:
              </p>
            </div>
            <div className="card p-5 text-left space-y-3">
              <p className="text-xs text-text-secondary font-mono">
                1. Open "Turn Windows features on or off"
              </p>
              <p className="text-xs text-text-secondary font-mono">
                2. Check "Windows Sandbox"
              </p>
              <p className="text-xs text-text-secondary font-mono">
                3. Restart your computer
              </p>
            </div>
            <p className="text-xs text-text-tertiary">
              Requires Windows Pro/Enterprise with virtualization enabled
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ─── Loading State ───
  if (sandboxAvailable === null) {
    return (
      <div className="flex flex-col h-full bg-bg-secondary">
        <div className="flex items-center justify-between px-4 py-2.5 bg-bg-secondary border-b border-border-primary">
          <div className="flex items-center gap-2.5">
            <Monitor size={15} className="text-accent" />
            <span className="text-sm font-medium text-text-primary">Sandbox</span>
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-3">
            <Loader2 size={28} className="text-text-tertiary animate-spin mx-auto" />
            <p className="text-sm text-text-tertiary">Checking Windows Sandbox...</p>
          </div>
        </div>
      </div>
    );
  }

  // ─── Main View ───
  return (
    <div className="flex flex-col h-full bg-bg-secondary relative">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-bg-secondary border-b border-border-primary flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <Monitor size={15} className="text-accent" />
          <span className="text-sm font-medium text-text-primary">Windows Sandbox</span>
          {sandboxRunning && (
            <span className="flex items-center gap-2 text-xs text-success bg-success/10 px-2.5 py-1 rounded-full font-medium">
              <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
              Live
            </span>
          )}
          {sandboxLaunching && (
            <span className="flex items-center gap-2 text-xs text-accent bg-accent-subtle px-2.5 py-1 rounded-full font-medium">
              <Loader2 size={11} className="animate-spin" />
              Starting...
            </span>
          )}
          {isRecording && sandboxRunning && (
            <span className="flex items-center gap-2 text-xs text-error bg-error/10 px-2.5 py-1 rounded-full font-medium">
              <span className="w-2 h-2 rounded-full bg-error animate-pulse" />
              REC
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {sandboxRunning && (
            <>
              {!isStreaming ? (
                <button
                  onClick={startStream}
                  className="px-3 py-2 text-xs font-medium text-accent bg-accent-subtle rounded-lg hover:bg-accent/20 transition-colors"
                  title="Start live video capture"
                >
                  <Wifi size={14} />
                </button>
              ) : (
                <button
                  onClick={stopStream}
                  className="px-3 py-2 text-xs font-medium text-text-tertiary bg-bg-elevated rounded-lg hover:text-text-secondary transition-colors"
                  title="Stop live capture"
                >
                  <WifiOff size={14} />
                </button>
              )}
              <button
                onClick={handleFocusSandbox}
                className="px-3 py-2 text-xs font-medium text-text-tertiary bg-bg-elevated rounded-lg hover:text-text-secondary transition-colors"
                title="Focus sandbox window"
              >
                <ExternalLink size={14} />
              </button>
              <button
                onClick={handleStop}
                className="px-3.5 py-2 text-xs font-medium bg-error/15 text-error rounded-lg hover:bg-error/25 transition-colors"
              >
                Stop
              </button>
            </>
          )}
          {!sandboxRunning && !sandboxLaunching && (
            <button
              onClick={() => setShowConfig(!showConfig)}
              className={`p-1.5 text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated rounded-md transition-colors
                ${showConfig ? 'text-accent bg-accent-subtle' : ''}`}
              title="Sandbox settings"
            >
              <Settings2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 relative overflow-hidden">
        {/* Live Video Stream */}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full h-full object-contain bg-black"
          style={{ display: isStreaming ? 'block' : 'none' }}
        />

        {/* Thumbnail Preview (when not streaming) */}
        {!isStreaming && sandboxRunning && thumbnailSrc && (
          <div
            className="w-full h-full flex items-center justify-center bg-black cursor-pointer group"
            onClick={handleFocusSandbox}
          >
            <img
              src={thumbnailSrc}
              alt="Windows Sandbox"
              className="max-w-full max-h-full object-contain"
            />
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
              <div className="opacity-0 group-hover:opacity-100 transition-opacity text-center space-y-3">
                <div className="w-14 h-14 rounded-full bg-black/20 backdrop-blur-sm flex items-center justify-center mx-auto">
                  <ExternalLink size={22} className="text-white" />
                </div>
                <p className="text-sm text-white font-medium">Click to enter sandbox</p>
                <p className="text-xs text-black/60">Or use live capture for in-app view</p>
              </div>
            </div>
          </div>
        )}

        {/* Sandbox Running but no thumbnail yet */}
        {!isStreaming && sandboxRunning && !thumbnailSrc && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-3">
              <Loader2 size={28} className="text-accent animate-spin mx-auto" />
              <p className="text-sm text-text-secondary">Connecting to sandbox...</p>
              <p className="text-xs text-text-tertiary">Capturing preview in a moment</p>
            </div>
          </div>
        )}

        {/* Stream Error */}
        {streamError && (
          <div className="absolute top-3 left-3 right-3 bg-error/10 border border-error/20 rounded-xl p-4 flex items-center gap-3">
            <AlertTriangle size={16} className="text-error flex-shrink-0" />
            <p className="text-sm text-error">{streamError}</p>
            <button
              onClick={() => setStreamError(null)}
              className="ml-auto text-error/60 hover:text-error text-xs"
            >
              ✕
            </button>
          </div>
        )}

        {/* Launching State */}
        {sandboxLaunching && !sandboxRunning && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="relative">
                <div className="w-20 h-20 rounded-2xl bg-accent/15 flex items-center justify-center mx-auto">
                  <Shield size={32} className="text-accent" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-bg-secondary flex items-center justify-center">
                  <Loader2 size={16} className="text-accent animate-spin" />
                </div>
              </div>
              <div>
                <p className="text-lg font-semibold text-text-primary">Starting Windows Sandbox</p>
                <p className="text-sm text-text-tertiary mt-1">
                  Initializing isolated environment...
                </p>
              </div>
              <div className="w-48 h-1 bg-bg-elevated rounded-full overflow-hidden mx-auto">
                <div className="h-full bg-accent rounded-full animate-pulse" style={{ width: '60%' }} />
              </div>
            </div>
          </div>
        )}

        {/* Idle State — Launch Button */}
        {!sandboxRunning && !sandboxLaunching && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-6 max-w-sm px-8">
              <div className="w-20 h-20 rounded-2xl bg-accent/15 flex items-center justify-center mx-auto">
                <Shield size={36} className="text-accent" />
              </div>
              <div>
                <p className="text-xl font-bold text-text-primary">Windows Sandbox</p>
                <p className="text-sm text-text-tertiary mt-2 leading-relaxed">
                  Launch an isolated Windows environment to safely test your agent. 
                  All changes are discarded when the sandbox closes.
                </p>
              </div>

              {/* Config panel */}
              {showConfig && (
                <div className="card p-5 text-left space-y-4">
                  <div className="flex items-center gap-2.5 text-sm text-text-primary font-medium">
                    <Settings2 size={14} />
                    Configuration
                  </div>
                  <div>
                    <label className="text-xs text-text-tertiary block mb-1.5">Memory (MB)</label>
                    <select
                      value={memoryMB}
                      onChange={(e) => setMemoryMB(Number(e.target.value))}
                      className="w-full bg-bg-tertiary border border-border-primary rounded-lg px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent/40 transition-colors"
                    >
                      <option value={2048}>2 GB</option>
                      <option value={4096}>4 GB (Recommended)</option>
                      <option value={8192}>8 GB</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2.5 text-xs text-text-tertiary">
                    <Shield size={12} />
                    Networking, clipboard, and vGPU are enabled
                  </div>
                </div>
              )}

              <button
                onClick={handleLaunch}
                className="btn-primary text-sm px-8 py-2.5"
              >
                <div className="flex items-center gap-2.5 justify-center">
                  <Play size={15} />
                  Launch Sandbox
                </div>
              </button>

              <p className="text-xs text-text-tertiary">
                First launch may take 15-30 seconds
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
