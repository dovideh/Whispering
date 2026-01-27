# Voice Commands: Dual-Model Feasibility Analysis

## Overview

Investigation into adding vocal command support to Whispering using a dual-model
approach: a fast/lightweight model for command detection and the existing large model
for prose transcription.

**Conclusion**: Feasible. The current architecture supports it cleanly. The recommended
starting point is pattern matching on existing `large-v3` output, with a second `tiny`
model evaluated later if latency is insufficient.

---

## Current Architecture (Relevant Parts)

### Transcription Pipeline

```
Mic → sounddevice → frame_queue → faster-whisper (local) → segments
  → paragraph detection → ts_queue (raw text)
  → optional Google Translate → tl_queue
  → optional AI (OpenRouter) → pr_queue
  → UI display / autotype (clipboard+paste) / TTS
```

### Key Facts

- Whisper runs **locally** (faster-whisper, models from `tiny` to `large-v3`)
- AI runs **remotely** via OpenRouter (excluded for command detection)
- `autotype.py` already does keyboard simulation via xdotool/pyautogui — can send
  arbitrary keystrokes including Ctrl+B, Ctrl+I, etc.
- The processing thread (`proc()` in `processing.py`) classifies segments into
  "done" (finalized) and "curr" (still being refined) — a natural decision point
- Output panels (`output.py`) currently use `ui.textarea` — **plain text only**

---

## Prerequisites

### Rich Text Output Panels

**Current state**: All three output panels (Whisper, AI, Translation) use NiceGUI's
`ui.textarea`, which renders plain text only. Formatting commands (bold, italic,
headings) would have no visible effect inside Whispering.

**Required change**: Replace `ui.textarea` with HTML-rendering components. Options:

| Approach | Pros | Cons |
|----------|------|------|
| `ui.html()` | Simple, renders any HTML | Not editable, no built-in scrolling |
| `ui.element('div')` + contenteditable | Editable, native HTML rendering | More complex event handling |
| Quasar `QEditor` (read-only) | Built-in toolbar, WYSIWYG | Heavier component, may be overkill |

**Recommended**: `ui.html()` inside a scrollable container for now. The panels are
read-only anyway. If editing is needed later, migrate to contenteditable div.

**Impact on existing code**:
- `bridge.py` `_update_text_buffer()` — needs to handle HTML content
- `output.py` `_copy_text()` / `_cut_text()` — strip HTML tags for clipboard
- `session_logger.py` — decide whether to store raw or formatted text
- `state.py` text buffers — store HTML strings instead of plain strings

---

## Command Detection Strategy

### Interception Point

Commands are intercepted in `bridge.py` inside `_update_text_buffer()` (line 438),
right before finalized text is appended to the state buffer:

```
done_text arrives from queue
    ↓
command_detector.check(done_text)
    ├── Contains command → extract command, execute action,
    │                       pass remaining text (minus command) to buffer
    └── No command → pass through unchanged
```

This is clean because:
- It's in the bridge layer (not in the core processing thread)
- It runs on the UI polling thread (100ms intervals)
- It doesn't touch the Whisper model or processing pipeline
- Commands are stripped before appearing in output panels

### False Positive Mitigation

Primary strategy: **Isolation heuristic**

If the entire finalized Whisper segment contains *only* a recognized command phrase
(with tolerance for punctuation/trailing spaces), treat it as a command. If the
phrase appears mid-sentence, it passes through as text.

This works because people naturally pause before and after commands, causing Whisper
to emit them as separate segments.

Alternative strategies (configurable):
1. **Prefix keyword**: "Command bold" triggers; "I need to be bold" doesn't
2. **Double-tap**: "Bold bold" triggers; single "bold" is text

### Multi-Language Support

Command triggers are defined per-language in the config. Since Whisper returns the
detected language (`info.language`), the detector knows which language column to
search:

```yaml
commands:
  bold:
    action: format_bold
    triggers:
      en: ["bold", "make bold", "make it bold"]
      he: ["מודגש", "הפוך למודגש"]
      fr: ["gras", "mettre en gras"]
    end_triggers:
      en: ["stop bold", "end bold"]
      he: ["הפסק מודגש"]
```

Matching is case-insensitive with punctuation stripped. Optional fuzzy matching
(e.g., rapidfuzz) to handle Whisper's occasional misspellings of short words.

---

## Command Categories

### Tier 1: Punctuation & Whitespace (Simplest)

| Voice Command | Action | Implementation |
|---------------|--------|----------------|
| "comma" | Insert `,` | Direct text substitution |
| "period" / "full stop" | Insert `.` | Direct text substitution |
| "question mark" | Insert `?` | Direct text substitution |
| "exclamation mark" | Insert `!` | Direct text substitution |
| "new line" | Insert `\n` / `<br>` | Text substitution |
| "new paragraph" | Insert `\n\n` / `<p>` | Text substitution |

These are **stateless** — detect, substitute, done.

### Tier 2: Text Formatting (Stateful)

| Voice Command | Action | State Machine |
|---------------|--------|---------------|
| "bold" / "start bold" | Activate bold | `BOLD_ACTIVE` state |
| "stop bold" / "end bold" | Deactivate bold | Return to `IDLE` |
| "italic" / "start italic" | Activate italic | `ITALIC_ACTIVE` state |
| "title one" / "heading one" | Next paragraph as H1 | `HEADING_1` state (auto-ends at paragraph break) |
| "title two" | Next paragraph as H2 | `HEADING_2` state |

State machine wraps incoming text in HTML tags:
- `BOLD_ACTIVE` → `<b>{text}</b>`
- `HEADING_1` → `<h1>{text}</h1>`, auto-resets at `\n\n`

Scoped commands ("bold the following paragraph") set the state with an auto-end
condition (next paragraph break).

### Tier 3: Macros (User-Defined Keystroke Sequences)

| Voice Trigger | Keystroke Sequence | Use Case |
|---------------|-------------------|----------|
| "sign off email" | Type "Best regards," + Enter + Enter + Type name | Email |
| "select all" | Ctrl+A | Editing |
| "undo" | Ctrl+Z | Editing |
| "save" | Ctrl+S | Any app |

Macros are defined in config as:

```yaml
macros:
  sign_off:
    triggers:
      en: ["sign off", "sign off email"]
    actions:
      - type: "Best regards,"
      - key: "Return"
      - key: "Return"
      - type: "David"
```

Executed via `autotype.py` which already supports both `type_text()` and
`_xdotool_key()` / `_pyautogui_key()` for arbitrary keystrokes.

### Tier 4: Navigation / System Commands (Complex)

| Voice Command | Action | Complexity |
|---------------|--------|------------|
| "go to google.com" | Open URL in browser | Low (`webbrowser.open()`) |
| "open settings" | Focus Whispering settings | Low (internal) |
| "switch tab" | Send Ctrl+Tab | Low (keystroke) |
| "scroll down" | Send Page Down | Low (keystroke) |
| "click Save button" | Find and click UI element | High (accessibility APIs) |

Simple navigation (URLs, keystrokes) is straightforward. Context-aware commands
that need to read another application's UI tree require accessibility APIs
(AT-SPI on Linux) — significant scope expansion, not recommended for initial
implementation.

---

## Autotype Integration for Formatting

When autotype is active and formatting commands are used, the executor needs to
send formatting keystrokes to the target application:

```
Command "bold" detected
  → If autotype active: send Ctrl+B to target app
  → Always: set BOLD_ACTIVE state for internal output panel

Text arrives while BOLD_ACTIVE
  → Internal panel: wrap in <b> tags
  → Autotype: paste text normally (bold already active in target)

Command "stop bold" detected
  → If autotype active: send Ctrl+B again to deactivate
  → Always: return to IDLE state
```

**Application-specific shortcuts** (e.g., Ctrl+Alt+1 for Heading 1 in Google Docs
vs. different shortcut in LibreOffice) can be handled via configurable keymaps in
the macro system.

---

## Configuration Structure

Commands live in their own config space, separate from personas:

```
config/
├── ai_config.yaml              # existing - AI models, prompts
├── custom_personas.yaml        # existing - AI personas
└── voice_commands.yaml         # NEW - all command definitions
```

Or if commands grow complex:

```
config/
├── commands/
│   ├── formatting.yaml         # bold, italic, headings
│   ├── punctuation.yaml        # comma, period, question mark
│   ├── navigation.yaml         # new line, new paragraph
│   └── macros.yaml             # user-defined macro sequences
```

Config loader follows the same pattern as `ai_config.py`.

---

## Dual Model Architecture (Phase 3 — Later Evaluation)

If `large-v3` latency for command detection proves problematic:

```
Audio Stream
    ├─── tiny model (parallel thread) ─── command detection (~50-100ms)
    └─── large-v3 model (main thread) ─── prose transcription (~1-3s CPU)
```

- `tiny` model: ~75MB RAM, near-instant on CPU
- Runs on same audio via second consumer on `frame_queue`
- When `tiny` detects a command phrase, executes immediately
- For non-commands, `tiny` output is discarded; `large-v3` output is used

**Synchronization challenge**: Avoid double-processing when both models see the
same segment. Solution: command segments detected by `tiny` are marked with a
timestamp; when `large-v3` produces overlapping segments, they're suppressed.

**Recommendation**: Start with pattern matching on `large-v3` output. Only add
the `tiny` model if command response time is noticeably slow in practice.

---

## New Source Files Required

| File | Purpose |
|------|---------|
| `config/voice_commands.yaml` | Command definitions with multi-language triggers |
| `src/commands_config.py` | YAML config loader (follows `ai_config.py` pattern) |
| `src/command_detector.py` | Pattern matcher + state machine |
| `src/command_executor.py` | Dispatches actions (HTML tags, keystrokes, macros) |

**Modified files**:

| File | Change |
|------|--------|
| `src/whispering_ui/components/output.py` | Replace `ui.textarea` with HTML rendering |
| `src/whispering_ui/bridge.py` | Add command detection in `_update_text_buffer()` |
| `src/whispering_ui/state.py` | Add command-related state fields |
| `src/whispering_ui/main.py` | Load command config on startup |
| `src/whispering_ui/components/sidebar.py` | Add voice commands toggle/settings |

---

## Implementation Phases

### Phase 1: Rich Text Output + Basic Commands
- Replace textarea with HTML rendering in all three panels
- Implement command detector with punctuation commands (comma, period, new line)
- `config/voice_commands.yaml` with English triggers
- Integration in bridge `_update_text_buffer()`

### Phase 2: Formatting Commands + State Machine
- Stateful commands (bold, italic, headings)
- Scoped commands ("bold the following paragraph")
- Multi-language trigger support
- Autotype formatting keystrokes (Ctrl+B, etc.)

### Phase 3: Macros
- User-defined keystroke sequences in config
- Macro executor via `autotype.py`
- Simple navigation commands (open URL, switch tab)

### Phase 4: Dual Model (If Needed)
- Second `tiny` Whisper model thread for fast command detection
- Only if Phase 1-3 testing reveals latency issues

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| False positives ("I need to be bold") | Isolation heuristic: command = entire segment |
| Whisper mangles short command words | Fuzzy matching, multiple trigger variants |
| HTML in text buffers breaks copy/paste | Strip tags before clipboard operations |
| Stateful commands leak across sessions | Reset state machine on recording stop |
| Target app uses different shortcuts for bold/headings | Configurable keymap per application in macros |
| Wayland doesn't support xdotool | Existing wtype/ydotool fallbacks (not strict requirement) |
