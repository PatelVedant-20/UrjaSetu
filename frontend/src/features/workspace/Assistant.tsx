import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Send, X, ArrowUpRight } from "lucide-react";
import { workspaceRequest } from "../../lib/api";

type Reply = {
  message: string;
  provider: string;
  links: { path: string; label: string }[];
};
type Message = {
  role: "user" | "assistant";
  text: string;
  links?: Reply["links"];
};
function UrjaFace() {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <g stroke="#edbc51" strokeWidth="4" strokeLinecap="round">
        {Array.from({ length: 8 }, (_, i) => (
          <path key={i} d="M32 3v5" transform={`rotate(${i * 45} 32 32)`} />
        ))}
      </g>
      <circle cx="32" cy="32" r="20" fill="#f5cb65" />
      <ellipse cx="24" cy="30" rx="2" ry="3" fill="#364f35" />
      <ellipse cx="40" cy="30" rx="2" ry="3" fill="#364f35" />
      <path
        d="M25 39q7 7 14 0"
        fill="none"
        stroke="#364f35"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="20" cy="36" r="3" fill="#ecaa70" />
      <circle cx="44" cy="36" r="3" fill="#ecaa70" />
    </svg>
  );
}

export function Assistant() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Hi, I'm Urja ☀️ Your little energy guide. Ask about your household, savings, tomorrow's forecast, or where to find something.",
    },
  ]);
  const [provider, setProvider] = useState("account-guide");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) end.current?.scrollIntoView({ block: "nearest" });
  }, [messages, open, pending]);
  async function send(text: string) {
    if (!text.trim() || pending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setPending(true);
    try {
      const response = await workspaceRequest<Reply>("/workspace/assistant", {
        message: text,
      });
      setProvider(response.provider);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: response.message, links: response.links },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text:
            e instanceof Error
              ? `I couldn't fetch your account details. ${e.message}`
              : "I couldn't connect. Please try again.",
        },
      ]);
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="ux-assistant">
      {open && (
        <section
          className="ux-chat"
          role="dialog"
          aria-label="Urja energy assistant"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          <header>
            <UrjaFace />
            <div>
              <strong>Urja</strong>
              <small>
                {provider === "gemini"
                  ? "AI energy assistant"
                  : "Your account guide"}
              </small>
            </div>
            <button aria-label="Close assistant" onClick={() => setOpen(false)}>
              <X size={18} />
            </button>
          </header>
          <div className="ux-chat-messages" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={`ux-chat-message ${m.role}`}>
                <p>{m.text}</p>
                {m.links?.map((link) => (
                  <Link
                    key={link.path}
                    to={link.path}
                    onClick={() => setOpen(false)}
                  >
                    {link.label}
                    <ArrowUpRight size={14} />
                  </Link>
                ))}
              </div>
            ))}
            {pending && (
              <div className="ux-chat-thinking">
                Checking your energy…<span>•••</span>
              </div>
            )}
            <div ref={end} />
          </div>
          <div className="ux-chat-suggestions">
            {["My savings", "Best time to sell", "How do I buy energy?"].map(
              (text) => (
                <button
                  key={text}
                  disabled={pending}
                  onClick={() => void send(text)}
                >
                  {text}
                </button>
              ),
            )}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
          >
            <input
              autoFocus
              aria-label="Message Urja"
              placeholder="Ask your energy guide…"
              maxLength={2000}
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
            <button
              aria-label="Send message"
              disabled={pending || !input.trim()}
            >
              <Send size={18} />
            </button>
          </form>
          <small className="ux-chat-footnote">
            Uses your account data · Trades always need your confirmation
          </small>
        </section>
      )}
      <button
        className="ux-chat-bubble"
        aria-label={open ? "Hide energy assistant" : "Open energy assistant"}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <UrjaFace />
        {!open && <span>Ask Urja</span>}
      </button>
    </div>
  );
}
