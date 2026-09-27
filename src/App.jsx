import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, MessageCircle, Mic, RotateCcw, Send, Sparkles, Volume2 } from 'lucide-react';

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:7860').replace(/\/$/, '');
const SESSION_KEY = 'dashthru_session_id';

const createSessionId = () => {
  const sessionId = crypto.randomUUID();
  sessionStorage.setItem(SESSION_KEY, sessionId);
  return sessionId;
};

const getSessionId = () => sessionStorage.getItem(SESSION_KEY) || createSessionId();

const STARTER_PROMPTS = [
  { intent: 'Greeting', label: 'Say hello', text: 'Hi there' },
  { intent: 'Order item', label: 'Build an order', text: 'I want 2 large pepperoni pizzas' },
  { intent: 'Add topping', label: 'Customize it', text: 'Add extra cheese to my last pizza' },
  { intent: 'Ask menu', label: 'See the menu', text: 'What veggie options are on the menu?' },
  { intent: 'Cancel item', label: 'Remove an item', text: 'Cancel my last order' },
  { intent: 'Checkout', label: 'Review the cart', text: 'I would like to checkout' },
  { intent: 'Confirm', label: 'Confirm the order', text: "Yes, that's correct" },
];

const MENU_CATALOG = [
  { name: 'Pizzas', items: ['Pepperoni', 'Margherita', 'Veggie', 'Meat lovers', 'Cheese'] },
  { name: 'Burgers', items: ['Classic burger', 'Cheeseburger', 'Veggie burger'] },
  { name: 'Coffee & drinks', items: ['Latte', 'Cappuccino', 'Cold brew', 'Americano', 'Mocha', 'Coke', 'Sprite'] },
  { name: 'Sides', items: ['Fries', 'Garlic bread', 'Chicken wings', 'Garden salad', 'Mozzarella sticks'] },
  { name: 'Desserts', items: ['Brownie', 'Cheesecake', 'Chocolate cake', 'Ice cream'] },
];

const initialMessages = [
  {
    id: 'welcome',
    role: 'assistant',
    title: 'BAY ASSISTANT',
    text: 'Hi! I can help you order an item, choose a menu option, add toppings, remove items, or check out.',
  },
  { id: 'prompt', role: 'assistant', text: 'Try saying: "I want two large pepperoni pizzas with extra cheese."' },
];

function App() {
  const [messages, setMessages] = useState(initialMessages);
  const [sessionId, setSessionId] = useState(getSessionId);
  const [mode, setMode] = useState('voice');
  const [inputText, setInputText] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [status, setStatus] = useState('Tap to start listening');
  const recognitionRef = useRef(null);
  const requestInFlightRef = useRef(false);
  const lastTranscriptRef = useRef({ text: '', time: 0 });
  const voiceFinalTranscriptRef = useRef('');
  const voiceTranscriptRef = useRef('');
  const voiceSilenceTimerRef = useRef(null);
  const submitVoiceRef = useRef(null);

  const addMessage = (message) => {
    setMessages((current) => [...current, { id: crypto.randomUUID(), ...message }]);
  };

  const askAssistant = async (text) => {
    const cleanText = text.trim();
    const now = Date.now();
    if (!cleanText || isThinking || requestInFlightRef.current) return;
    if (lastTranscriptRef.current.text === cleanText && now - lastTranscriptRef.current.time < 2500) return;

    lastTranscriptRef.current = { text: cleanText, time: now };
    requestInFlightRef.current = true;

    addMessage({ role: 'user', text: cleanText });
    setIsThinking(true);
    setStatus('Sending to the kitchen...');

    try {
      const response = await fetch(`${API_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: cleanText, session_id: sessionId }),
      });

      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const data = await response.json();
      addMessage({ role: 'assistant', text: data.reply, intent: data.intent });
    } catch (error) {
      addMessage({
        role: 'assistant',
        error: true,
        text: 'I could not reach the kitchen right now. Please try again.',
      });
    } finally {
      requestInFlightRef.current = false;
      setIsThinking(false);
      setStatus('Tap to start listening');
    }
  };

  const startListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus('Voice input needs Chrome or Edge');
      return;
    }

    if (isListening) {
      submitVoiceRef.current?.();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;
    let submittedForThisSession = false;

    const finishVoiceInput = () => {
      if (submittedForThisSession) return;
      window.clearTimeout(voiceSilenceTimerRef.current);
      const transcript = voiceTranscriptRef.current.trim();
      if (transcript.length < 3) {
        recognition.stop();
        setIsListening(false);
        setStatus('Please say a complete request');
        return;
      }
      submittedForThisSession = true;
      submitVoiceRef.current = null;
      recognition.stop();
      askAssistant(transcript);
    };

    submitVoiceRef.current = finishVoiceInput;
    recognition.onstart = () => {
      voiceFinalTranscriptRef.current = '';
      voiceTranscriptRef.current = '';
      window.clearTimeout(voiceSilenceTimerRef.current);
      setIsListening(true);
      setStatus('Listening... speak a complete request');
    };
    recognition.onresult = (event) => {
      if (submittedForThisSession) return;
      let interimTranscript = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result?.[0]?.transcript?.trim() || '';
        if (result.isFinal) {
          voiceFinalTranscriptRef.current = `${voiceFinalTranscriptRef.current} ${transcript}`.trim();
        } else {
          interimTranscript = `${interimTranscript} ${transcript}`.trim();
        }
      }

      voiceTranscriptRef.current = `${voiceFinalTranscriptRef.current} ${interimTranscript}`.trim();
      if (!voiceTranscriptRef.current) return;
      window.clearTimeout(voiceSilenceTimerRef.current);
      voiceSilenceTimerRef.current = window.setTimeout(finishVoiceInput, 1800);
    };
    recognition.onerror = () => {
      window.clearTimeout(voiceSilenceTimerRef.current);
      submitVoiceRef.current = null;
      setStatus('Try again when you are ready');
      setIsListening(false);
    };
    recognition.onend = () => {
      if (!submittedForThisSession && voiceTranscriptRef.current.trim().length >= 3) {
        finishVoiceInput();
        return;
      }
      window.clearTimeout(voiceSilenceTimerRef.current);
      setIsListening(false);
      recognitionRef.current = null;
      submitVoiceRef.current = null;
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  useEffect(() => () => {
    window.clearTimeout(voiceSilenceTimerRef.current);
    recognitionRef.current?.stop();
  }, []);

  const handleTextSubmit = (event) => {
    event.preventDefault();
    if (!inputText.trim()) return;
    askAssistant(inputText);
    setInputText('');
  };

  const clearChat = () => {
    window.clearTimeout(voiceSilenceTimerRef.current);
    recognitionRef.current?.stop();
    submitVoiceRef.current = null;
    voiceFinalTranscriptRef.current = '';
    voiceTranscriptRef.current = '';
    requestInFlightRef.current = false;
    lastTranscriptRef.current = { text: '', time: 0 };
    setSessionId(createSessionId());
    setMessages(initialMessages);
    setInputText('');
    setIsListening(false);
    setIsThinking(false);
    setStatus('Tap to start listening');
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="wordmark">Dash<span>Thru</span></div>
          <span className="brand-divider" />
          <span className="brand-subtitle">VOICE DRIVE-THRU</span>
        </div>
        <div className="topbar-actions">
          <div className="kitchen-status"><span className="status-dot" /> KITCHEN LIVE</div>
          <button className="clear-button" onClick={clearChat} type="button" title="Clear chat">
            <RotateCcw size={15} /> New customer
          </button>
        </div>
      </header>

      <div className="model-notice" role="note">
        <span className="model-notice-label">IMPORTANT</span>
        <p>For the best results, use a short, specific request with correct spelling. DashThru uses a DistilBERT intent classifier, not a general-purpose LLM.</p>
        <span className="model-notice-example">Example: “I want 2 large pepperoni pizzas.”</span>
      </div>

      <section className="hero" aria-labelledby="page-title">
        <div className="hero-copy">
          <p className="eyebrow">WELCOME TO DASHTHRU</p>
          <h1 id="page-title">Order it<br /><em>your way.</em></h1>
          <p className="hero-description">Tell us what you&apos;re craving. Use your voice or type it out, and we&apos;ll take it from there.</p>
        </div>
        <div className="hero-aside">
          <span className="aside-line" />
          <p>Fast, friendly ordering<br />for the road ahead.</p>
        </div>
      </section>

      <section className="capability-strip" aria-label="Things you can ask DashThru to do">
        <div className="capability-intro">
          <span>YOUR ORDER ASSISTANT</span>
          <p>Speak or type naturally. DashThru can help with:</p>
        </div>
        <div className="capability-list">
          <span>Menu questions</span><span>New orders</span><span>Toppings</span><span>Remove items</span><span>Checkout</span><span>Confirmation</span>
        </div>
      </section>

      <section className="workspace" aria-label="DashThru ordering assistant">
        <section className="chat-panel" aria-live="polite">
          <div className="conversation-head">
            <div>
              <span className="section-kicker">YOUR ORDER</span>
              <h2>Let&apos;s get this started.</h2>
            </div>
            <span className="secure-label">READY TO HELP</span>
          </div>

          <div className="message-list">
            {messages.map((message) => (
              <article className={`message ${message.role} ${message.error ? 'error' : ''}`} key={message.id}>
                {message.title && <span className="message-title">{message.title}</span>}
                <p>{message.text}</p>
                {message.intent && <span className="intent-tag">{message.intent.replaceAll('_', ' ')}</span>}
              </article>
            ))}
            {isThinking && <article className="message assistant thinking"><span /><span /><span /></article>}
          </div>

          <div className="composer">
            <div className="mode-tabs" role="tablist" aria-label="Choose how to order">
              <button className={mode === 'voice' ? 'active' : ''} onClick={() => setMode('voice')} role="tab" type="button" aria-selected={mode === 'voice'}>
                <Mic size={16} /> Voice
              </button>
              <button className={mode === 'chat' ? 'active' : ''} onClick={() => setMode('chat')} role="tab" type="button" aria-selected={mode === 'chat'}>
                <MessageCircle size={16} /> Chat
              </button>
            </div>

            {mode === 'voice' ? (
              <>
                <button className={`voice-button ${isListening ? 'listening' : ''}`} onClick={startListening} type="button" aria-label={isListening ? 'Stop listening' : 'Speak your order'}>
                  <span className="mic-icon"><Mic size={21} /></span>
                  <span className="voice-copy"><strong>{isListening ? 'Listening...' : 'Speak your order'}</strong><small>{isListening ? "I'm listening for your order" : status}</small></span>
                  <ArrowUpRight className="composer-arrow" size={21} />
                </button>
                <p className="voice-example"><span>TRY SAYING</span> "I want two large pepperoni pizzas with extra cheese."</p>
              </>
            ) : (
              <form className="text-composer" onSubmit={handleTextSubmit}>
                <input value={inputText} onChange={(event) => setInputText(event.target.value)} placeholder="Try: 2 large pepperoni pizzas with olives" aria-label="Type your order" />
                <button type="submit" aria-label="Send message" disabled={!inputText.trim() || isThinking}><Send size={18} /></button>
              </form>
            )}
            <p className="privacy-note"><Volume2 size={14} /> Your conversation stays focused on getting your order right.</p>
          </div>
          <section className="starter-section" aria-labelledby="starter-heading">
          <div className="starter-heading">
            <div>
              <span className="section-kicker">GET STARTED</span>
              <h2 id="starter-heading">Try one of these prompts.</h2>
            </div>
            <p>Each example demonstrates something the assistant can understand.</p>
          </div>
          <div className="starter-grid">
            {STARTER_PROMPTS.map((prompt) => (
              <button key={prompt.intent} className="starter-card" onClick={() => askAssistant(prompt.text)} type="button">
                <span className="starter-intent">{prompt.intent}</span>
                <strong>{prompt.label}</strong>
                <span className="starter-text">"{prompt.text}"</span>
                <ArrowUpRight size={17} />
              </button>
            ))}
          </div>
          </section>
        </section>

        <aside className="assist-panel">
          <div className="assist-heading"><Sparkles size={17} /><span>EXPLORE THE MENU</span></div>
          <p className="assist-description">Browse the available categories, then tap any item to send it into your order conversation.</p>
          <section className="menu-section" aria-labelledby="menu-heading">
            <div className="menu-section-label"><span>ON THE MENU</span><small>Tap an item to order</small></div>
            <h2 id="menu-heading">Choose your craving.</h2>
            <div className="menu-grid">
              {MENU_CATALOG.map((category) => (
                <div className="menu-category" key={category.name}>
                  <h3>{category.name}</h3>
                  <div className="menu-items">
                    {category.items.map((item) => (
                      <button className="menu-item" key={item} onClick={() => askAssistant(`I want ${item}`)} type="button">
                        <span>{item}</span><ArrowUpRight size={13} />
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
          <div className="assist-rule" />
          <div className="assist-tip"><span>01</span><p>Use the same conversation to add toppings, remove an item, or check out.</p></div>
        </aside>
      </section>

      <footer className="footer-note">
        <span>DashThru</span>
        <span>Good food. No waiting around.</span>
        <a href="https://github.com/guth01/DashThru" target="_blank" rel="noreferrer">
          <ArrowUpRight size={13} /> View source on GitHub
        </a>
        <span>© 2026</span>
      </footer>
    </main>
  );
}

export default App;
