# Academia - Cloud

An upskilling academy for a practice (here: Microsoft Cloud Security). The engine is generic; every piece of content —
courses, videos, learning paths, the skills catalog, the practice definition and the news sources — is data you edit in
Excel, in CSV or in the app's **✏️ Edit mode**. Nothing is hard-coded. The app is **English only**.

## Run it (Windows)
Double-click **`Academia Cloud.bat`**. The first time it prepares the environment (1–3 minutes) and leaves an
«Academia Cloud» shortcut on the desktop. Close the black window to stop the app.

Manual run:
```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Progress is stored in `data\academy.db` (`set ACADEMY_DB=...` for another path). Tests: `pip install pytest` and `pytest`.
If the PDF buttons are greyed out, close the app and run **`Install components.bat`** once.

## What learners see
| Tab | What it does |
|---|---|
| Learning route | Per skill family: vendor → skill → class 1, 2, 3… (Microsoft Learn first, then the vendor's own path or Workday Learning). Mark each step done. |
| Course | Lesson (summary, key points, practice) + 3 check questions + a compact video panel that stays in view. |
| Glossary | Term ↔ definition quiz and search. |
| Video library | Every video by topic and the lessons that use it. |
| Progress & badges | Ranks, badges, the path for your role, recent activity. |
| Skills map | Families by gap, their champion and which lessons cover each skill. |
| Certifications | Your current and desired certifications; exam preparation (study, practice, mock exam). |
| Forum | Ask the experts (SMEs) of a family; champions and owners run it. |
| Rhythm | My next sessions (with Outlook invites), study groups to join, and the meeting room: an agenda built from the data plus action items. |
| Knowledge exchange | A reading bank of security news from the sources the practice follows (Microsoft, cloud providers, vendors, NIST, CIS, ISO 27001, CISA…). |

When the app opens, a window shows the **latest Microsoft security news** (title, short summary, a medium-size image and
links to the publisher). It closes with «Continue to the academy» and shows once per session.

Owners and champions also get **Reports** (status by family, who keeps up with the career path, certifications; Excel and
**PDF**) and **Demand** (what the role requests ask for against the practice and the courses, with the weekly trend; CSV
and **PDF**). Owners get **Team** (measurements, notices, the content file, access, AI assistant).

## Rhythm: the meetings that keep it alive
| Series | Who | Default | The agenda brings |
|---|---|---|---|
| Monthly review | Owner lead + every champion | 1st Tuesday, 10:00, 60 min | Families in red, people behind, certifications expiring, **demand against the bench** (most requested practice skills, people at level 3+, whether a course exists), study groups running, open actions |
| Family sync | The family's champion and members | Every Thursday, 30 min | The family's progress, people to follow up, forum questions waiting, a rotating 5-minute demo, the certifications the family asks for |
| Study group | 4–8 people, one certification, **an exam date** | Weekly until the exam | Session n of N, this session's topic (the exam's modules spread over the sessions, then a mock exam and a final review), each member's best mock score against the pass mark |

- Owners create the recommended rhythm with one button; champions create their family's sync and open study groups; anyone joins an open group (people who aim for that certification see it first).
- Every series downloads as an **.ics invitation** (recurrence, attendees with e-mail, 15-minute reminder) to open in Outlook.
- Every meeting ends with **actions** (what, who, by when); the open ones lead the next agenda. The agenda downloads as text to paste in Teams.

## Team inventory: certifications and skills
- One collection file for the whole team: **`team_inventory_template.xlsx`** (drop-down lists and instructions) or **`.csv`**, one row per
  certification or skill: `Person, Email, Type, Name, Code, Vendor, Level, Years, Status, Obtained, Expires, EvidenceUrl, Notes`.
- `Type = certification` goes to the certification register (Code, current / desired, dates, Credly link); `Type = skill` goes to the skills
  inventory with the same 1–5 scale for everyone: 1 Aware · 2 Basic · 3 Practitioner · 4 Advanced · 5 Expert.
- Free skill names are matched to the catalog through the practice's aliases (KQL → Microsoft Sentinel, PowerShell → Automation…).
- Reports → **Skills matrix**: download the template, import the filled file (replaces the inventory of the people in it), the person × skill
  matrix, **«Who can take this role?»** (skills + minimum level → people, levels and certifications) and the champion's validation (✓).
- Each person keeps theirs in Certifications → **My skills**; changing a level removes its validation.

## Edit mode (owners)
Every section has a **✏️ Edit mode** switch at the top. On, the section shows the tables it is made of:

| Section | Tables |
|---|---|
| Learning route / Skills map | LearningPaths, Skills, Families |
| Course | Lessons, Questions, LessonResources (videos of each lesson), Levels, Courses |
| Glossary | Glossary |
| Video library | Resources, Topics |
| Progress & badges | Ranks, Roles |
| Certifications | What each family requires and everyone's register |
| Reports | Families (champions, gap) |
| Demand | PracticeSkills, PracticeRoles, Practice |
| Knowledge exchange | NewsSources |
| Team | Every table, by section |

- Columns that point to something else (course, lesson, video, topic, family, skill, level) are **drop-down lists** of what exists.
- Fixed values (correct letter, kind, scope, severity, yes/no) are drop-down lists of those values.
- Repeated free values (channel, provider, category, vendor, champion…) list the values already used; **➕ New option for a list** adds one.
- Columns with several values (skills, aliases) take several choices and accept new ones typed in the cell.
- Add rows at the bottom of a table; select rows to delete them. New rows get their id from their name when left empty.
- **💾 Save changes** runs exactly the checks of an imported file. With a problem nothing is saved and the problems are
  listed; otherwise the files are written (after a backup in `data\content_backups\`) and the Excel content file is rewritten.

## The content file
`content\academy_content.xlsx` holds everything, one tab per table, grouped by section (the tab color shows the section;
the README tab is the index). Edit it in Excel, save, close Excel and reopen the app: it is checked in full and applied only
if it is right. The same content travels as one CSV (`python tools\content.py export content.csv`, column `Table`).

| Section | Tabs |
|---|---|
| Skills catalog | Families, Skills, LearningPaths |
| Practice | Practice, PracticeSkills, PracticeRoles, NewsSources |
| Courses | Courses, Levels, Ranks, Topics, Roles |
| Lessons | Lessons, Questions |
| Videos and links | Resources, LessonResources |
| Glossary | Glossary |

Rules: each lesson has 3 questions with 4 distinct options and `AnswerLetter` A–D, and at least 2 videos from 2 channels.
Files from earlier versions (Spanish tab names, a `Lang` column, the retired `VBD` tab) are still read: only the English
rows are kept.

## News sources (per practice)
`catalog\news_sources.csv` — also the NewsSources tab and the Knowledge exchange edit mode:

`Name, Category, Url, FeedUrl, Splash, Enabled, Description`

- `FeedUrl` is the RSS / Atom feed; without one (or when it does not answer) the card shows the site's own preview.
- `Splash = yes` marks the source whose latest item opens the academy (Microsoft Security Insider; its items come from the
  Microsoft Security blog feed).
- Readings are cached for an hour and the last good one is kept in `data\news_cache.json`, so the bank works offline.
  Text from the internet is shown as plain text; only https links and images are used.

Another practice (ServiceNow, SAP…) replaces the catalog, the practice tables and this CSV; the engine stays the same.

## Demand analysis
Reads the roles report of the organization (CSV or Excel export, 36 columns; only Role ID, Role Title and Role Primary
Skill are mandatory, the rest are used when present). It understands the report as it comes: skills written as
`1 - Skill name (P2 - Intermediate)` (the number and the proficiency are separated from the name), coded titles such as
`123456-00001_Solution Architect`, US dates (`9/15/2026`) and `5-Nov-26`, `-` as an empty cell, and the column
**Matrix cross-skills Practice** (shown in the tab *Gaps per role (matrix)* and in the PDF).

**The report is confidential**: an uploaded file is only read in memory for the session and nothing is saved. An owner
can choose *Save it in the app* to keep it in `content\demand_roles.csv` and `content\demand_history\` (by date) and
follow the weekly trend. `content\demand_roles_sample.csv` has made-up roles to try it.

**Executive report (owners).** The Demand tab gives owners an *Executive summary* (on screen) and the **Executive report
(PDF)**: two pages with the key messages, the top 10 practice skills against the bench (people at level 3+ in the team
inventory) and the courses, the recommended actions with the champion who owns each one, the trend against the previous
upload and the roles by start month. It works on a file read for the session too (compared with the saved uploads) and
says so on the cover. The *Detailed report (PDF)* keeps every chart and table.

## Azure App Service
`deploy/azure/startup.py` (startup command: `python deploy/azure/startup.py`), `deploy/azure/package.py` (the zip to deploy: no data, config or roles
files) and `.github/workflows/main_academia-cloud-test.yml` (Deployment Center's workflow: tests, package and deploy on every push to main). With `ACADEMY_AUTH=entra` the
app takes the person signed in by Microsoft Entra ID (App Service Authentication) and gives roles by the e-mail in People.
Everything the app writes lives in `/home/academy-data`. Step-by-step guide: the doc «Academia - Cloud: deploy on Azure
App Service».

## English only
Earlier versions kept Spanish and English side by side. On the first start, `academy/english.py` converts once: the
English course and exam become the only files, Spanish videos are dropped, and the content and demand files get their
English names. Everything replaced is copied first to `data\content_backups\<date>-english\`. Progress is kept (lessons
and questions have the same ids).

## Files
| Path | What it is |
|---|---|
| `app.py` | Entry point (sidebar, views, content sync, English migration) |
| `academy/page.py` | The page: tabs and sections |
| `academy/editor.py` | ✏️ Edit mode |
| `academy/content_xlsx.py`, `content_sync.py` | The content workbook: export, import, checks, sync |
| `academy/news.py`, `news_page.py` | News sources, feed reading, opening window, Knowledge exchange |
| `academy/report.py`, `report_pdf.py` | Reports by family and their Excel / PDF |
| `academy/demand.py`, `demand_page.py`, `demand_pdf.py`, `demand_exec.py` | Demand analysis, trend, detailed and executive PDF |
| `academy/progress.py`, `route.py`, `exam.py` | Points, ranks, badges; learning route; certification prep |
| `academy/forum.py`, `certs.py` | Forum; certification register |
| `packs/<id>/pack.json` | A course (`packs/_template/` is the skeleton for a new one) |
| `catalog/` | `skills.json`, `materials.json` (learning paths), `practice.json`, `news_sources.csv` |
| `tools/` | `content.py` (export / check / import), `validate_pack.py`, `audit_videos.py`, `export_sharepoint.py` |

## People and roles (catalog/people.csv)
`Person, Email, Role, Families, Active` — Role = owner | champion | sme | learner; Families = family ids separated by `;`.
The sidebar offers these names in **Who are you?**: your role comes with your name (owners get the **Owner view** switch).
Up to **3 owners** (ACADEMY_MAX_OWNERS changes it): an owner names them in **Team → 👑 App owners**, with the work
e-mail each one signs in with; they are saved in People with role `owner`.
A champion listed here becomes the champion of those families in the catalog (reports and notices copy them). Also the
People tab of the content workbook and ✏️ Edit mode (Team, Reports). Owners in `config/access.json` (with the optional PIN)
keep working.

## Study material (catalog/study_material.csv)
`Title, Url, Source, Category, Theme, Kind, Level, SkillId, Notes` — Kind = video | playlist | search | page.
Shown in **Knowledge exchange → 📚 Study material** (filters by category, theme and text; each item opens the author's site)
and at the end of the **Video library** (videos play inside the app). It starts with John Savill's Technical Training
(Microsoft): 6 exact videos, his Azure Master Class, certification study crams and the themes of the practice as searches
inside his channel, and his video index. To load **every** video of his index: open https://www.azadvertizer.net/savill.html,
save it (File → Save as… → HTML) and upload it in *Study material tools*; every YouTube link becomes an item, with the
heading above it as the theme. Champions select items and **Add to the learning path** of a skill.

## Each family's career path (champions)
In **Learning route**, the champion of a family (and owners) get **🧭 Manage the career path**: a table of every class of the
family with **Status = required** (part of the path, counts for progress) | **optional** (recommended material) | **off**
(kept in the plan, hidden from learners), the class order, kind, provider, minutes and notes. They can upload their own
material (PowerPoint, PDF, Word, Excel, video): it becomes a class learners download. The same path is a CSV per family,
`content/families/<family-id>.csv` (`SkillId, Skill, Class, Title, Url, Kind, Provider, Status, Minutes, Notes`): edit it in
Excel and reopen the app (it is checked first), or download / upload it in the panel. The files, `catalog/materials.json` and
the LearningPaths tab of the content workbook always match.
