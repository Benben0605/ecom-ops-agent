import { FormEvent, KeyboardEvent, useRef, useState } from "react";

import { sendChat } from "../api";
import MarkdownContent from "../components/MarkdownContent";

interface ChatMessage { id: number; role: "user" | "assistant"; content: string; pending?: boolean; error?: boolean }

export default function Playground() {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const nextId = useRef(1);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || pending) return;
    const userMessage = { id: nextId.current++, role: "user" as const, content: text };
    const pendingId = nextId.current++;
    setMessages((current) => [...current, userMessage, { id: pendingId, role: "assistant", content: "正在思考…", pending: true }]);
    setInput("");
    setPending(true);
    try {
      const response = await sendChat({ session_id: sessionId, user_input: text });
      setSessionId(response.session_id);
      setMessages((current) => current.map((message) => message.id === pendingId ? { ...message, content: response.assistant_message, pending: false } : message));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "请求失败";
      setMessages((current) => current.map((item) => item.id === pendingId ? { ...item, content: `发送失败：${message}`, pending: false, error: true } : item));
    } finally {
      setPending(false);
    }
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); }
  };
  const reset = () => { setSessionId(""); setMessages([]); setInput(""); };

  return <section className="playground panel">
    <header className="playground-status"><div><span className="online-dot" /><b>Agent 在线</b><span className="session-label">session · {sessionId ? `${sessionId.slice(0, 8)}…` : "首条消息后创建"}</span></div><button type="button" onClick={reset} disabled={pending}>＋ 新会话</button></header>
    <div className="chat-stream" aria-live="polite">
      {!messages.length && <div className="chat-empty"><div className="chat-empty-mark">◆</div><h2>开始一次运营任务</h2><p>可以查询订单、检索客服知识、推荐商品或分析运营数据。</p><div className="prompt-examples">{["查一下订单 A1001 的状态", "推荐 300 元以内的护肤品", "分析最近的 GMV 和热销商品"].map((example) => <button type="button" key={example} onClick={() => setInput(example)}>{example}</button>)}</div></div>}
      {messages.map((message) => <div className={`chat-row chat-${message.role}`} key={message.id}><div className="chat-avatar">{message.role === "user" ? "你" : "◆"}</div><div className={`chat-bubble${message.pending ? " pending" : ""}${message.error ? " error" : ""}`}>{message.role === "assistant" && !message.pending && !message.error ? <MarkdownContent content={message.content} /> : message.content}{message.pending && <span className="typing-dots"><i /><i /><i /></span>}</div></div>)}
    </div>
    <form className="chat-composer" onSubmit={(event) => void submit(event)}><textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={onKeyDown} placeholder="输入消息… Enter 发送，Shift + Enter 换行" disabled={pending} rows={1} /><button type="submit" disabled={!input.trim() || pending}>{pending ? "发送中" : "发送"}<svg viewBox="0 0 24 24"><path d="m4 4 17 8-17 8 4-8-4-8Zm4 8h13" /></svg></button></form>
  </section>;
}
