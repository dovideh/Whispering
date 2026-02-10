#!/usr/bin/env python3

import argparse
import curses
import threading

import core
from cmque import PairDeque, Queue
from session_logger import SessionLogger

# AI modules (optional)
try:
    from ai_config import load_ai_config
    from ai_provider import AITextProcessor
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# Voice command modules (optional)
try:
    from commands_config import load_voice_commands_config
    from command_detector import CommandDetector
    from command_executor import CommandExecutor
    VOICE_COMMANDS_AVAILABLE = True
except ImportError:
    VOICE_COMMANDS_AVAILABLE = False


class Pad:
    def __init__(self, h, w, t, l):
        self.pad = curses.newpad(h * 2, w)
        self.h, self.w, self.t, self.l = h, w, t, l
        self.res_queue = Queue(PairDeque())
        self.add_done("> ")
        self.refresh()

    def refresh(self):
        self.pad.refresh(0, 0, self.t, self.l, self.t + self.h - 1, self.l + self.w - 1)

    def load_pos(self):
        self.pad.move(self.y, self.x)
        self.pad.clrtobot()

    def add_curr(self, curr):
        self.pad.attron(curses.A_UNDERLINE | curses.A_DIM)
        self.pad.addstr(curr)
        self.pad.attroff(curses.A_UNDERLINE | curses.A_DIM)
        y, x = self.pad.getyx()
        if y >= self.h:
            t = y - self.h + 1
            self.pad.scrollok(True)
            self.pad.scroll(t)
            self.pad.scrollok(False)
            self.pad.move(y - t, x)
            self.y -= t
        self.last += curr

    def add_done(self, done):
        self.pad.scrollok(True)
        self.pad.addstr(done)
        self.pad.scrollok(False)
        y, x = self.pad.getyx()
        if y >= self.h:
            t = y - self.h + 1
            self.pad.scrollok(True)
            self.pad.scroll(t)
            self.pad.scrollok(False)
            self.pad.move(y - t, x)
        self.y, self.x = self.pad.getyx()
        self.last = ""

    def update(self, command_detector=None, command_executor=None):
        while self.res_queue:
            res = self.res_queue.get()
            if res is not None:
                done, curr = res
                # Voice command detection on finalized text
                if command_detector and command_executor and done:
                    result = command_detector.check(done)
                    if result is not None:
                        replacement = command_executor.execute(result)
                        done = replacement if replacement is not None else ""
                    # Suppress curr if it looks like a pending command
                    if curr and command_detector.check(curr) is not None:
                        curr = ""
                self.load_pos()
                self.add_done(done)
                self.add_curr(curr)
            else:
                done = self.last
                self.load_pos()
                self.add_done(done)
                self.add_done("\n")
                self.add_done("> ")
        self.refresh()


def _draw_borders(stdscr, t, b, l, r, dividers):
    """Draw box borders and vertical dividers."""
    stdscr.hline(t, l + 1, curses.ACS_HLINE, r - l - 1)
    stdscr.hline(b, l + 1, curses.ACS_HLINE, r - l - 1)
    stdscr.vline(t + 1, l, curses.ACS_VLINE, b - t - 1)
    stdscr.vline(t + 1, r, curses.ACS_VLINE, b - t - 1)
    stdscr.addch(t, l, curses.ACS_ULCORNER)
    stdscr.addch(b, l, curses.ACS_LLCORNER)
    stdscr.addch(t, r, curses.ACS_URCORNER)
    stdscr.addch(b, r, curses.ACS_LRCORNER)
    for d in dividers:
        stdscr.vline(t + 1, d, curses.ACS_VLINE, b - t - 1)
        stdscr.addch(t, d, curses.ACS_TTEE)
        stdscr.addch(b, d, curses.ACS_BTEE)


def _create_ai_processor(ai_persona, ai_model_index, source, target):
    """Create AI processor if AI modules are available and configured."""
    if not AI_AVAILABLE:
        return None
    try:
        ai_config = load_ai_config()
        if not ai_config:
            return None

        # Get selected model
        models = ai_config.get_models()
        if ai_model_index >= len(models):
            ai_model_index = 0
        selected_model_id = models[ai_model_index]['id']

        # Determine mode and persona
        persona_id = ai_persona or "proofread"
        personas = ai_config.get_personas()
        persona = None
        for p in personas:
            if p['id'] == persona_id:
                persona = p
                break
        if persona is None:
            persona_id = "proofread"

        if persona_id == "proofread":
            if target:
                mode = "proofread_translate"
            else:
                mode = "proofread"
        else:
            mode = "custom"

        processor = AITextProcessor(
            config=ai_config,
            model_id=selected_model_id,
            mode=mode,
            source_lang=source,
            target_lang=target,
            persona_id=persona_id if mode == "custom" else None
        )
        return processor
    except Exception as e:
        print(f"[WARN] AI init failed: {e}", flush=True)
        return None


def _init_voice_commands(source_language):
    """Initialize voice command detector and executor."""
    if not VOICE_COMMANDS_AVAILABLE:
        return None, None
    try:
        config = load_voice_commands_config()
        if config:
            lang = source_language if source_language else None
            detector = CommandDetector(config, language=lang)
            executor = CommandExecutor()
            return detector, executor
    except Exception:
        pass
    return None, None


def show(mic, model, vad, memory, patience, timeout, prompt, source, target,
         device, para_detect=True, para_threshold_std=1.5, para_min_pause=0.8,
         para_max_chars=500, para_max_words=100, enable_logging=True,
         ai_enabled=False, ai_persona=None, ai_model_index=0,
         ai_trigger_mode="time", ai_process_interval=20, ai_process_words=150,
         voice_commands=False, auto_stop_minutes=0, autotype_mode="Off"):

    # Session logger (JSONL)
    session_logger = SessionLogger(log_dir="logs") if enable_logging else None

    # AI processor
    ai_processor = None
    if ai_enabled:
        ai_processor = _create_ai_processor(ai_persona, ai_model_index, source, target)
        if ai_processor:
            print(f"[INFO] AI: mode={ai_processor.mode}, persona={ai_persona}", flush=True)
        else:
            print("[WARN] AI enabled but processor could not be created", flush=True)

    # Voice commands
    command_detector, command_executor = (None, None)
    if voice_commands:
        command_detector, command_executor = _init_voice_commands(source)

    # Autotype
    autotype_fn = None
    if autotype_mode != "Off":
        try:
            import autotype as _autotype_mod
            autotype_fn = _autotype_mod.type_text
        except ImportError:
            pass

    # Determine layout: how many panes do we need?
    has_ai_pane = ai_processor is not None and ai_processor.mode in ("proofread", "proofread_translate", "custom")
    has_tl_pane = target is not None
    pane_count = 1 + int(has_ai_pane) + int(has_tl_pane)

    stdscr = curses.initscr()
    curses.setupterm()
    curses.curs_set(0)
    curses.noecho()
    stdscr.clear()
    stdscr.timeout(100)
    h, w = curses.LINES, curses.COLS
    t = 1
    b = h - 1
    l = 0
    r = w - 2

    # Compute column boundaries
    if pane_count == 1:
        dividers = []
        cols = [(l, r)]
    elif pane_count == 2:
        m = w // 2 - 1
        dividers = [m]
        cols = [(l, m), (m, r)]
    else:
        m1 = w // 3 - 1
        m2 = 2 * w // 3 - 1
        dividers = [m1, m2]
        cols = [(l, m1), (m1, m2), (m2, r)]

    _draw_borders(stdscr, t, b, l, r, dividers)

    # Create pads for each pane
    pane_idx = 0
    cl, cr = cols[pane_idx]
    ts_win = Pad(b - t - 1, cr - cl - 3, t + 1, cl + 2)
    pane_idx += 1

    pr_win = None
    if has_ai_pane:
        cl, cr = cols[pane_idx]
        pr_win = Pad(b - t - 1, cr - cl - 3, t + 1, cl + 2)
        pane_idx += 1

    tl_win = None
    if has_tl_pane:
        cl, cr = cols[pane_idx]
        tl_win = Pad(b - t - 1, cr - cl - 3, t + 1, cl + 2)

    # Queues
    ts_queue = ts_win.res_queue
    tl_queue = tl_win.res_queue if tl_win else Queue(PairDeque())
    pr_queue = pr_win.res_queue if pr_win else None

    # Determine whether to use Google Translate
    use_google_translate = ai_processor is None

    ready = [None]
    error = [None]
    level = [0]
    manual_trigger = [False]
    auto_stop_enabled = auto_stop_minutes > 0

    # Build key help
    keys = ["<Space> Start/Stop", "<Q> Quit"]
    if ai_processor and ai_trigger_mode == "manual":
        keys.append("<A> AI Process")
    instr = " " + " ".join(f"<{k.split('>')[0][1:]}> {k.split('> ')[1]}" if '>' in k else k for k in keys)
    instr = " " + "  ".join(keys)

    state = "Stopped"
    log_request_id = None

    while True:
        status = state
        if error[0] and state == "Stopped":
            status = f"Error: {error[0][:40]}"
        elif log_request_id and state.startswith("Started"):
            status = f"{state} (Logging)"

        # Truncate status line to fit
        status_line = status + " " * max(0, r - l + 1 - len(status) - len(instr)) + instr
        stdscr.addstr(0, l, status_line[:r - l + 1])
        stdscr.refresh()

        # Update panes - voice commands only on whisper pane
        ts_win.update(command_detector, command_executor)
        if pr_win:
            pr_win.update()
        if tl_win:
            tl_win.update()

        key = stdscr.getch()

        if key == ord("q") or key == ord("Q"):
            # Finalize logging
            if session_logger and log_request_id:
                session_logger.finalize_session("manual")
                log_request_id = None
            break

        elif (key == ord("a") or key == ord("A")) and ai_processor and ai_trigger_mode == "manual":
            manual_trigger[0] = True

        elif state.startswith("Stopped"):
            if key == ord(" "):
                ready[0] = False
                error[0] = None

                # Start session logging
                if session_logger:
                    config = {
                        "model": model, "vad_enabled": vad,
                        "para_detect_enabled": para_detect, "device": device,
                        "source_language": source or "auto",
                        "target_language": target or "none",
                        "ai_enabled": ai_enabled,
                        "voice_commands": voice_commands,
                        "auto_stop_minutes": auto_stop_minutes,
                        "autotype_mode": autotype_mode,
                    }
                    if ai_processor:
                        config["ai_persona"] = ai_persona
                        config["ai_trigger_mode"] = ai_trigger_mode
                    log_request_id = session_logger.start_session(config)

                # Get mic index
                mic_index = core.get_mic_index(mic) if mic else core.get_default_device_index()

                # core.proc kwargs
                kwargs = {
                    'ai_processor': ai_processor,
                    'ai_process_interval': ai_process_interval,
                    'ai_process_words': ai_process_words if ai_trigger_mode == "words" else None,
                    'ai_trigger_mode': "manual" if (ai_processor and ai_trigger_mode == "manual") else ai_trigger_mode,
                    'prres_queue': pr_queue,
                    'auto_stop_enabled': auto_stop_enabled,
                    'auto_stop_minutes': auto_stop_minutes,
                    'manual_trigger': manual_trigger,
                    'use_google_translate': use_google_translate,
                }

                threading.Thread(
                    target=core.proc,
                    args=(mic_index, model, vad, memory, patience, timeout,
                          prompt, source, target, ts_queue, tl_queue, ready,
                          device, error, level, para_detect, para_threshold_std,
                          para_min_pause, para_max_chars, para_max_words),
                    kwargs=kwargs,
                    daemon=True
                ).start()
                state = "Starting..."

        elif state.startswith("Started"):
            if key == ord(" "):
                ready[0] = False
                state = "Stopping..."

        elif state.startswith("Stopping..."):
            if ready[0] is None:
                if session_logger and log_request_id:
                    session_logger.finalize_session("manual")
                    log_request_id = None
                state = "Stopped"

        elif state.startswith("Starting..."):
            if ready[0] is True:
                state = "Started"
            if ready[0] is None:
                state = "Stopped"

    curses.endwin()


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe and translate speech in real-time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
keyboard controls:
  Space      Start/Stop recording
  Q          Quit
  A          Trigger AI processing (manual mode only)

examples:
  %(prog)s                              # Basic transcription
  %(prog)s --target es                  # Transcribe and translate to Spanish
  %(prog)s --ai --ai-persona proofread  # AI proofreading
  %(prog)s --voice-commands             # Enable voice commands
  %(prog)s --auto-stop 10              # Auto-stop after 10 min silence
"""
    )

    # Core transcription
    parser.add_argument("--mic", type=str, default=None, help="microphone device name")
    parser.add_argument("--model", type=str, choices=core.models, default="large-v3", help="Whisper model size")
    parser.add_argument("--vad", action="store_true", help="enable voice activity detection")
    parser.add_argument("--memory", type=int, default=3, help="number of previous segments for prompt context")
    parser.add_argument("--patience", type=float, default=5.0, help="seconds to wait before finalizing a segment")
    parser.add_argument("--timeout", type=float, default=5.0, help="timeout for the translation service")
    parser.add_argument("--prompt", type=str, default="", help="initial prompt for transcription")
    parser.add_argument("--source", type=str, default=None, choices=core.sources, help="source language (auto-detect if omitted)")
    parser.add_argument("--target", type=str, default=None, choices=core.targets, help="target language for translation")
    parser.add_argument("--device", type=str, default="cuda", choices=core.devices, help="inference device (cpu, cuda, auto)")

    # Paragraph detection
    para = parser.add_argument_group("paragraph detection")
    para.add_argument("--no-para", action="store_true", help="disable adaptive paragraph detection")
    para.add_argument("--para-threshold", type=float, default=1.5, help="std devs above mean for paragraph break")
    para.add_argument("--para-min-pause", type=float, default=0.8, help="minimum pause for paragraph break (seconds)")
    para.add_argument("--para-max-chars", type=int, default=500, help="max characters per paragraph")
    para.add_argument("--para-max-words", type=int, default=100, help="max words per paragraph")

    # AI processing
    ai = parser.add_argument_group("AI processing")
    ai.add_argument("--ai", action="store_true", help="enable AI text processing")
    ai.add_argument("--ai-persona", type=str, default="proofread", help="AI persona id (proofread, qa, or custom id)")
    ai.add_argument("--ai-model", type=int, default=0, help="AI model index from ai_config.yaml")
    ai.add_argument("--ai-trigger", type=str, default="time", choices=["time", "words", "manual"], help="AI trigger mode")
    ai.add_argument("--ai-interval", type=int, default=20, help="seconds between AI triggers (time mode)")
    ai.add_argument("--ai-words", type=int, default=150, help="word count between AI triggers (words mode)")

    # Voice commands
    vc = parser.add_argument_group("voice commands")
    vc.add_argument("--voice-commands", action="store_true", help="enable voice command detection")

    # Auto-stop
    parser.add_argument("--auto-stop", type=int, default=0, metavar="MINUTES", help="auto-stop after N minutes of silence (0=disabled)")

    # Autotype
    parser.add_argument("--autotype", type=str, default="Off", choices=["Off", "Whisper", "Translation", "AI"], help="auto-type output to active window")

    # Logging
    parser.add_argument("--no-log", action="store_true", help="disable session logging")

    args = parser.parse_args()

    show(
        mic=args.mic, model=args.model, vad=args.vad,
        memory=args.memory, patience=args.patience, timeout=args.timeout,
        prompt=args.prompt, source=args.source, target=args.target,
        device=args.device,
        para_detect=not args.no_para,
        para_threshold_std=args.para_threshold,
        para_min_pause=args.para_min_pause,
        para_max_chars=args.para_max_chars,
        para_max_words=args.para_max_words,
        enable_logging=not args.no_log,
        ai_enabled=args.ai,
        ai_persona=args.ai_persona,
        ai_model_index=args.ai_model,
        ai_trigger_mode=args.ai_trigger,
        ai_process_interval=args.ai_interval,
        ai_process_words=args.ai_words,
        voice_commands=args.voice_commands,
        auto_stop_minutes=args.auto_stop,
        autotype_mode=args.autotype,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
