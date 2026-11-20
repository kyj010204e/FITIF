import { useEffect, useRef, useState, type FormEvent } from "react";
import { AudioLines, History, Mic, Plus, Send, Square, Volume2 } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import "./ChatPage.css";

type Message = { role: "user" | "assistant"; content: string };
type Conversation = { id: string; messages: Message[] };
type VoiceResult = { isFinal: boolean; 0: { transcript: string } };
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<VoiceResult> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
type SpeechWindow = Window & {
  SpeechRecognition?: new () => Recognition;
  webkitSpeechRecognition?: new () => Recognition;
};

function loadConversations(key: string): Conversation[] {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((thread) =>
      typeof thread?.id === "string" && Array.isArray(thread.messages)
      && thread.messages.every((message: Message) =>
        (message?.role === "user" || message?.role === "assistant") && typeof message.content === "string"
      )
    );
  } catch {
    return [];
  }
}

function ChatRoom({ token, memberId }: { token: string; memberId: number }) {
  const storageKey = `fitif:gemma-chat:${memberId}`;
  const [conversations, setConversations] = useState(() => loadConversations(storageKey));
  const [activeId, setActiveId] = useState<string | undefined>(() => conversations[0]?.id);
  const [input, setInput] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [listening, setListening] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [voiceStatus, setVoiceStatus] = useState("");
  const [storageError, setStorageError] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const request = useRef<AbortController | null>(null);
  const active = conversations.find((thread) => thread.id === activeId);
  const speech = window as SpeechWindow;
  const RecognitionClass = speech.SpeechRecognition ?? speech.webkitSpeechRecognition;
  const canSpeak = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

  useEffect(() => {
    let failed = false;
    try {
      localStorage.setItem(storageKey, JSON.stringify(conversations));
    } catch {
      failed = true;
    }
    if (failed) {
      // React 상태로는 계속 대화할 수 있고, 기록 저장 실패를 사용자에게 표시한다.
      const timer = window.setTimeout(() => setStorageError(true), 0);
      return () => window.clearTimeout(timer);
    }
  }, [conversations, storageKey]);

  useEffect(() => () => {
    const mic = recognition.current;
    recognition.current = null;
    if (mic) mic.abort();
    request.current?.abort();
    window.speechSynthesis?.cancel();
  }, []);

  function speak(text: string) {
    if (!canSpeak) {
      setVoiceStatus("이 브라우저에서 음성 재생을 사용할 수 없어요.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "ko-KR";
    utterance.onerror = ({ error: kind }) => {
      if (kind !== "canceled" && kind !== "interrupted") {
        setVoiceStatus("음성 재생이 막혔어요. 답변의 ‘듣기’를 눌러 주세요.");
      }
    };
    utterance.onstart = () => setVoiceStatus("");
    window.speechSynthesis.speak(utterance);
  }

  function updateConversation(id: string, messages: Message[]) {
    setConversations((current) => [{ id, messages }, ...current.filter((thread) => thread.id !== id)]);
  }

  async function send(text: string, spoken = false, retry = false) {
    if (request.current || recognition.current) return;
    const trimmed = text.trim().slice(0, 1200);
    if (!trimmed) return;

    const id = activeId ?? crypto.randomUUID();
    const messages: Message[] = retry && active
      ? active.messages
      : [...(active?.messages ?? []), { role: "user", content: trimmed }];
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    setVoiceStatus("");
    setActiveId(id);
    setInput("");
    window.speechSynthesis?.cancel();
    updateConversation(id, messages);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ messages: messages.slice(-11).map(({ role, content }) => ({ role, content: content.slice(0, 2500) })) }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(response.status === 401 ? "다시 로그인해 주세요."
          : typeof data?.detail === "string" ? data.detail : "Gemma에 연결하지 못했어요.");
      }
      if (typeof data?.answer !== "string" || !data.answer.trim()) throw new Error("답변을 받아오지 못했어요.");
      if (!controller.signal.aborted) {
        updateConversation(id, [...messages, { role: "assistant", content: data.answer }]);
        if (spoken) speak(data.answer);
      }
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "질문을 보내지 못했어요.");
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  function startOrStopVoice() {
    if (recognition.current) {
      recognition.current.stop();
      return;
    }
    if (!RecognitionClass || request.current) return;
    if (!window.isSecureContext) {
      setError("마이크를 사용하려면 FITIF의 HTTPS 주소로 접속해 주세요.");
      return;
    }

    window.speechSynthesis?.cancel();
    setError("");
    setVoiceStatus("");
    setShowHistory(false);
    const mic = new RecognitionClass();
    let transcript = "";
    let failed = false;
    mic.lang = "ko-KR";
    mic.interimResults = false;
    mic.continuous = false;
    mic.onresult = ({ results }) => {
      transcript = Array.from(results).filter((result) => result.isFinal)
        .map((result) => result[0].transcript).join(" ").trim();
    };
    mic.onerror = ({ error: kind }) => {
      if (recognition.current !== mic) return;
      failed = true;
      setError(kind === "not-allowed" || kind === "service-not-allowed"
        ? "브라우저에서 마이크 권한을 허용해 주세요."
        : "음성을 인식하지 못했어요. 다시 말하거나 아래에 입력해 주세요.");
    };
    mic.onend = () => {
      if (recognition.current !== mic) return;
      recognition.current = null;
      setListening(false);
      if (!failed && transcript) void send(transcript, true);
      else if (!failed) setError("인식된 말이 없어요. 다시 말해 주세요.");
    };

    recognition.current = mic;
    try {
      mic.start();
      setListening(true);
    } catch {
      recognition.current = null;
      setError("마이크를 시작하지 못했어요. 브라우저 권한을 확인해 주세요.");
    }
  }

  function selectConversation(id?: string) {
    window.speechSynthesis?.cancel();
    setActiveId(id);
    setInput("");
    setError("");
    setVoiceStatus("");
    setShowHistory(false);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  const lastQuestion = active?.messages.at(-1);
  return (
    <section className="voice-chat" aria-labelledby="voice-chat-title">
      <header className="voice-chat__header">
        <div className="voice-chat__heading"><AudioLines size={22} aria-hidden="true" /><h1 id="voice-chat-title">FITIF AI</h1></div>
        <div className="voice-chat__actions">
          <button type="button" onClick={() => setShowHistory(!showHistory)} aria-expanded={showHistory} disabled={pending || listening}>
            <History size={17} aria-hidden="true" /> 기록
          </button>
          <button type="button" onClick={() => selectConversation()} disabled={pending || listening}>
            <Plus size={17} aria-hidden="true" /> 새 대화
          </button>
        </div>
      </header>
      {showHistory && (
        <section className="voice-chat__history" aria-label="이전 대화">
          {conversations.length === 0 && <p>저장된 대화가 없어요.</p>}
          {conversations.map((thread) => (
            <button key={thread.id} type="button" aria-pressed={thread.id === activeId} onClick={() => selectConversation(thread.id)}>
              {thread.messages[0]?.content || "새 대화"}
            </button>
          ))}
        </section>
      )}
      <div className="voice-chat__messages" role="log" aria-label="대화 메시지" aria-live="polite">
        {!active?.messages.length && <p className="voice-chat__intro">마이크를 눌러 FITIF AI에게 물어보세요.</p>}
        {active?.messages.map((message, index) => (
          <article key={index} className={`voice-chat__message voice-chat__message--${message.role}`} aria-label={message.role === "user" ? "내 질문" : "FITIF AI 답변"}>
            <p>{message.content}</p>
            {message.role === "assistant" && canSpeak && (
              <button type="button" onClick={() => speak(message.content)} disabled={listening}>
                <Volume2 size={16} aria-hidden="true" /> 듣기
              </button>
            )}
          </article>
        ))}
        {pending && <p role="status" className="voice-chat__status">Gemma가 답변을 준비하고 있어요.</p>}
      </div>
      {error && <p role="alert" className="voice-chat__error">{error}</p>}
      {error && lastQuestion?.role === "user" && !pending && !listening && (
        <button type="button" onClick={() => void send(lastQuestion.content, true, true)}>다시 보내기</button>
      )}
      {voiceStatus && <p role="status">{voiceStatus}</p>}
      {storageError && <p role="status">이 브라우저에 대화 기록을 저장할 수 없어요.</p>}
      <form className="voice-chat__composer" onSubmit={submit}>
        <button type="button" className="voice-chat__mic" aria-label={listening ? "음성 입력 완료" : "마이크로 질문"}
          aria-pressed={listening} onClick={startOrStopVoice} disabled={!RecognitionClass || pending}>
          {listening ? <Square size={19} aria-hidden="true" /> : <Mic size={22} aria-hidden="true" />}
        </button>
        <input aria-label="질문" placeholder="질문 입력" value={input} maxLength={1200} disabled={listening}
          onChange={(event) => setInput(event.target.value)} />
        <button type="submit" aria-label="질문 보내기" disabled={!input.trim() || pending || listening}>
          <Send size={19} aria-hidden="true" />
        </button>
      </form>
      {listening
        ? <p role="status" className="voice-chat__hint">듣고 있어요. 말을 마치거나 정지 버튼을 눌러 주세요.</p>
        : <p className="voice-chat__hint">{RecognitionClass
          ? "음성 인식은 브라우저 서비스가 처리해요. 팀 테스트에는 가상 정보를 사용해 주세요."
          : "이 브라우저에서는 음성 인식을 사용할 수 없어요. 질문을 입력해 주세요."}</p>}
    </section>
  );
}

export default function ChatPage() {
  const { member, token } = useAuth();
  return member && token ? <ChatRoom key={member.member_id} memberId={member.member_id} token={token} /> : null;
}
