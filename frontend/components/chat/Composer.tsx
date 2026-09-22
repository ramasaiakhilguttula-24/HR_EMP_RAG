"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, SendHorizontal, Square } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

interface Props {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({ busy, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceOk, setVoiceOk] = useState(false);
  const recogRef = useRef<any>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SR) return;
    const recog = new SR();
    recog.lang = "en-IN";
    recog.interimResults = true;
    recog.onresult = (e: any) => {
      const transcript = Array.from(e.results).map((r: any) => r[0].transcript).join("");
      setText(transcript);
    };
    recog.onend = () => setListening(false);
    recogRef.current = recog;
    setVoiceOk(true);
    return () => {
      try {
        recog.abort();
      } catch {
        /* already stopped */
      }
    };
  }, []);

  const toggleMic = () => {
    if (!recogRef.current) return;
    if (listening) {
      recogRef.current.stop();
    } else {
      setText("");
      recogRef.current.start();
      setListening(true);
    }
  };

  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
    boxRef.current?.focus();
  };

  return (
    <div className="rounded-2xl border border-slate-300/60 bg-white/80 p-2 shadow-card backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/80">
      <label htmlFor="chat-input" className="sr-only">Ask an HR question</label>
      <textarea
        id="chat-input"
        ref={boxRef}
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
          }
        }}
        placeholder={listening ? "Listening… speak now" : "Ask about leave, benefits, conduct… (Shift+Enter for newline)"}
        className="max-h-36 w-full resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-slate-400"
      />
      <div className="flex items-center gap-1 px-1 pb-0.5">
        <button
          onClick={toggleMic}
          aria-label={listening ? "Stop voice input" : "Voice input"}
          title={voiceOk ? "Voice input" : "Voice input not supported in this browser"}
          disabled={!voiceOk}
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-xl transition-colors disabled:opacity-40",
            listening
              ? "animate-pulse bg-red-500/15 text-red-500"
              : "text-slate-500 hover:bg-slate-200/60 hover:text-brand-600 dark:text-slate-400",
          )}
        >
          {listening ? <MicOff size={17} /> : <Mic size={17} />}
        </button>
        <span className="ml-1 hidden text-[11px] text-slate-400 sm:inline">
          {busy ? "Prism is answering…" : "Answers cite HR policy sources"}
        </span>
        <div className="ml-auto flex gap-1.5">
          {busy ? (
            <Button variant="danger" onClick={onStop} className="!px-3.5 !py-2">
              <Square size={14} /> Stop
            </Button>
          ) : (
            <Button onClick={send} disabled={!text.trim()} className="!px-4 !py-2">
              <SendHorizontal size={15} /> Send
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
