# cpp-mentor

An **anti-cheat C & C++ teaching agent** for a fresher, powered by Google Gemini.

It teaches a fixed **90-day curriculum** (C → C++ → Data Structures & Algorithms →
Systems/Tooling → Capstone & Interview Prep), sized for **1 to 1.5 hours per day**.
It generates **fresh, personalized exercises** that can't be found online,
**compiles and tests the learner's code** (the strongest anti-cheat — you can't
fake a passing binary), logs study time, and pushes a **daily report** to a
**web dashboard** and **email**.

> **New here? Start with [Part A — First-time setup](#part-a--first-time-setup-do-this-once).**
> It walks you through everything from zero.

## The 90-day plan (1 to 1.5 hours per day)

Each day has only one or two small topics so the fresher can go deep rather than
rushing. The plan is split into five phases:

| Phase | Days | Focus |
|-------|------|-------|
| 1. C Fundamentals | 1–24 | Setup → variables → loops → functions → pointers → memory → structs → files → mini project |
| 2. C++ Core | 25–48 | Classes → OOP → STL → modern C++ → mini project |
| 3. Data Structures & Algorithms | 49–70 | Big-O → linked lists → stacks/queues → hash → trees → graphs → sorting → DP → greedy |
| 4. Systems, Tooling & Design | 71–80 | Memory model → threads → CMake → debugging → SOLID → design patterns |
| 5. Capstone & Interview Prep | 81–90 | Capstone project → mock interviews → final assessment |

The full topic-by-topic breakdown lives in `curriculum.json`.

---

# Part A — First-time setup (do this once)

You need three things installed: **Python**, a **C/C++ compiler**, and the
**project's packages**. Then you set your **Gemini API key**. That's it.

## A1. Install Python

1. Go to <https://www.python.org/downloads/> and download the latest Python 3.10+ for Windows.
2. Run the installer. **IMPORTANT:** on the first installer screen, tick the box
   **"Add python.exe to PATH"** before clicking *Install Now*.
3. Open a **new** terminal (PowerShell) and check:
   ```powershell
   python --version
   ```
   You should see something like `Python 3.12.x`. If you get a message about the
   Microsoft Store, close the terminal and reopen it (PATH changes need a new
   terminal).

## A2. Install a C/C++ compiler (MinGW-w64)

1. Go to <https://winlibs.com> and download the latest **WinLibs** build
   (a `.zip` file, e.g. `winlibs-x86_64-posix-seh-gcc-...-mingw-w64-...-zip`).
2. Unzip it somewhere permanent, e.g. `C:\mingw64`.
3. Add `C:\mingw64\bin` to your system PATH:
   - Press the Windows key, type **"Environment Variables"**, open
     *Edit the system environment variables*.
   - Click **Environment Variables…** → under *System variables* select **Path**
     → **Edit** → **New** → type `C:\mingw64\bin` → OK all the way out.
4. Open a **new** terminal and check:
   ```powershell
   gcc --version
   g++ --version
   ```
   Both should print a version number.

## A3. Get the project

If you cloned it from GitHub:
```powershell
git clone https://github.com/<your-username>/cpp-mentor.git
cd cpp-mentor
```
(If you copied the folder instead, just `cd` into it.)

## A4. Install the Python packages

```powershell
pip install -r requirements.txt
```

## A5. Set your Gemini API key

1. Get a key from <https://aistudio.google.com/apikey> (sign in with the Google
   account that has the Gemini subscription).
2. Set it as an environment variable:
   ```powershell
   setx GEMINI_API_KEY "AIza..."
   ```
   (Replace `AIza...` with your actual key.)
3. **Close and reopen the terminal** — `setx` only affects new terminals.
4. Verify:
   ```powershell
   echo $env:GEMINI_API_KEY
   ```
   It should print your key.

## A6. Configure email (for the daily report)

Open `config.yaml` and edit the `email:` section:
- `username` / `from` / `to` — your Gmail address.
- `password` — a **Gmail App Password** (not your real password):
  1. Go to <https://myaccount.google.com/apppasswords>.
  2. You may need to enable 2-Step Verification first.
  3. Create an app password (16 characters) and paste it into `config.yaml`.

If you don't want email yet, set `email.enabled: false` — the dashboard still works.

## A7. Run the self-test ✅

This is the single command that tells you whether everything is working:
```powershell
python -m cpp_mentor selftest
```
It checks Python, packages, compilers, the Gemini key, the curriculum, and does
a real end-to-end compile-and-test. Read the output:

- **`RESULT: ALL CHECKS PASSED`** → you're ready. 🎉
- Any **`[FAIL]`** lines → fix that item (the message tells you how) and re-run.
- **`[WARN]`** lines are non-fatal (e.g. "skipping live API call").

To also test a live call to Gemini (uses a tiny bit of your quota):
```powershell
python -m cpp_mentor selftest --live
```

---

# Part B — Daily routine (what the fresher does)

Every study day, in this order:

```powershell
# 1. Start logging study time (leave this terminal open)
python -m cpp_mentor.session_logger start

# 2. Study with the mentor (in a second terminal)
python -m cpp_mentor study
```

Inside `study`, the fresher chats with the mentor. Useful commands they can type:

| Command | What it does |
|---------|--------------|
| `/exercise` | Generate a fresh coding problem for the current topic |
| `/quiz` | Take a short quiz on the current topic |
| `/done` | Mark the current topic complete |
| `/next` | Move to the next day |
| `/status` | Show progress |
| `/help` | List commands |
| `/quit` | Exit (progress is saved) |

**When an exercise is generated**, the fresher writes code to the file path shown,
then verifies it:
```powershell
python -m cpp_mentor submit <exercise-id>
```
The agent **compiles and runs hidden tests** on the code. It only counts as
passed if the program actually works. After 3 failed attempts the reference
solution is shown (counts as half credit).

**At the end of the day:**
```powershell
python -m cpp_mentor.session_logger stop     # save the time log
python -m cpp_mentor report --send           # build + email the daily report
```

---

# Part C — Monitoring (what you do)

## Web dashboard
```powershell
python -m cpp_mentor.dashboard
```
Open **http://localhost:8000** — you'll see study hours, exercises passed, quiz
averages, and **cheat-risk flags** per day. (Port is set in `config.yaml`.)

> The dashboard binds to `127.0.0.1`, so only the machine it runs on can reach
> it. To view it from your own laptop, run a tunnel on the fresher's machine:
> `ngrok http 8000` (free at <https://ngrok.com>), then open the URL ngrok gives you.

## Email
Every `report --send` emails you a summary with a risk level (low / medium /
high) and any anomalies.

---

# Part D — How the anti-cheat works

| Layer | What it catches |
|-------|-----------------|
| **Verified code** | The program must compile and pass hidden tests. You can't fake a working binary. |
| **Personalized problems** | Gemini generates fresh numbers/names per learner per day — not findable online, not shareable. |
| **Similarity check** | Submitted code is compared to the reference solution; >85% match is flagged as a possible copy. |
| **Time vs output cross-check** | Logged hours are compared to actual work produced; big mismatch is flagged. |
| **Late-night / missing-session flags** | Sessions at odd hours or work without a logged session are flagged. |

No local software is 100% tamper-proof, but faking *verified, randomized,
explained* work every single day is far harder than faking a timer. The report
gives you a **risk level** so you know which days to probe with a live
"explain your code" call.

---

# Part E — Troubleshooting

| Symptom | Fix |
|---------|-----|
| `python` opens the Microsoft Store | You didn't tick "Add to PATH" — reinstall Python with that box checked, or use the full path to `python.exe`. |
| `gcc` / `g++` not recognized | The MinGW `bin` folder isn't on PATH, or you didn't open a **new** terminal after adding it. |
| `No Gemini API key found` | You didn't set `GEMINI_API_KEY`, or you set it but didn't reopen the terminal. |
| `pip` not recognized | Run `python -m pip install -r requirements.txt` instead. |
| Dashboard won't start | Run `python -m cpp_mentor selftest` to see which package is missing. |
| Email fails | Check the App Password in `config.yaml`; Gmail rejects the real account password. |
| Something is just broken | Run `python -m cpp_mentor selftest` — it pinpoints the failing layer. |

---

## Project layout

```
cpp-mentor/
├── config.yaml            # your settings (API key env, email, compiler, anti-cheat)
├── curriculum.json        # the 90-day plan (5 phases)
├── exercises.json         # static exercise bank (used as fallback / examples)
├── requirements.txt
└── cpp_mentor/
    ├── teacher.py         # the teaching agent CLI (study / exercise / submit / quiz)
    ├── selftest.py        # one-command health check
    ├── gemini_client.py   # Gemini API wrapper
    ├── exercises_gen.py   # personalized exercise + quiz generation
    ├── verify.py          # compile & test + similarity (anti-cheat core)
    ├── session_logger.py  # local study-time logger
    ├── report.py          # daily report + email
    ├── dashboard.py       # FastAPI web dashboard
    ├── state.py           # progress persistence (data/state.json)
    └── templates/index.html
```

## Notes & limitations

- The session logger samples the foreground window title (Windows) — it's a
  signal, not proof. The verified work is the real check.
- Gemini model is set in `config.yaml` (`gemini.model`). `gemini-2.5-flash` is
  a good default; switch to a stronger model if you want harder problems.
- All progress is stored locally in `data/` on the fresher's machine.
