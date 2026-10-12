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

## Two views: 🎓 Learning and 🛠️ Management
The sidebar's **View** switch appears only to people with something to manage. Learners never see the management tools.

**🎓 Learning** (everyone, including owners and champions when they learn):

| Tab | What it does |
|---|---|
| Learning route | The person's role family and job role: vendor → learning path (with its certification) → skill → module → course. Each course opens where it lives (SharePoint, Percipio, Workday MyLearning, the vendor's site, a repo or a file of the academy) and is marked done here. |
| Progress | 📈 points, badges and rank · 🏅 my certifications (current and desired) · 🧠 my skills · 📝 exam preparation (study, practice, mock exam). |
| Forum | Ask the experts (SMEs) of a family; champions and owners answer and moderate in place. |
| Study groups | The study groups of the person's role family (and the ones open to the whole practice), opened by its champion or the owners: next sessions with Outlook invites, join / leave, the group's agenda and actions. |
| Knowledge exchange | News, study material (and the glossary / video library of the course) for the person's role family and for the whole practice. |

When the app opens, a window shows the **latest Microsoft security news** once per session.

**🛠️ Management** — each person sees only the tools they are responsible for:

| Tab | Who | What |
|---|---|---|
| Learning paths | Owners (every family), champions (their families) | Job roles, learning paths, skills, courses and certifications on / off (✏️ Edit mode for owners). |
| Team | Upskilling & learning (everyone), champions (their families' people) | Roster and job roles, progress, notices to send. |
| Reports | Upskilling & learning | Status by family, who keeps up with the path, certifications, skills matrix; Excel and PDF. |
| Certifications | Owners, Upskilling & learning | What each family and job role asks for, everyone's register, exam questions (AI drafts). |
| Demand | Demand | The role requests against the practice and the courses, trend, executive PDF. |
| Skills map | Owners | Families by gap and the catalog import. |
| Rhythm | Owners, Upskilling & learning, champions | Monthly review, family syncs, study groups (by role family), meeting room. |
| Knowledge exchange | Upskilling & learning | News sources and study material, and the families each one is for. |
| Administration | Owners | Content workbook, every table, owners, responsibilities, practices, AI assistant. |

**Responsibilities** are set in People (column `Responsibilities` = `demand` and / or `learning`) or in **Administration →
👑 People and access → 🧭 Responsibilities**. While nobody of a practice holds one, the practice's owners do. An optional
PIN (Administration → Access) is asked before the Management view opens.

## Edit mode (owners)
In the 🛠️ Management view, Learning paths, Team, Demand and Skills map have a **✏️ Edit mode** switch; Knowledge exchange
edits its sources and material, and **Administration → ✏️ Every table** edits every table of the workbook (glossary, videos,
ranks…). The tables of each part:

| Management tab | Tables |
|---|---|
| Learning paths | LearningPaths, Skills, Paths, JobRoles, Vendors, Families |
| Team | Families, People |
| Demand | PracticeSkills, PracticeRoles, Practice |
| Skills map | Families, Skills, Paths, LearningPaths |
| Knowledge exchange | NewsSources, StudyMaterial |
| Administration → Every table | Every table, by section (glossary, videos, ranks, course roles…) |

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

## Practices
Each practice of the organization (Microsoft Cloud Security, PPM…) is its own space: courses, role families and skills,
learning paths, demand, study material, news sources and its own content workbook. The first practice lives in the app
folder as always; every other one in `practices/<id>/` with the same folders. The list is `catalog/practices.csv`.

* **Global owners** (role owner with an empty Practice in People) pick any practice in the sidebar and add new ones in
  **Team → 🏢 Practices**. A new practice starts with an empty catalog and a first course without lessons, ready to fill
  in ✏️ Edit mode.
* Everyone else belongs to one practice (column **Practice** of `catalog/people.csv`; empty = the first practice) and
  only sees that one. Each practice can have up to 6 owners of its own (**Team → 👑 Owners of …**).
* The People sheet of a practice's workbook lists that practice's people; saving it leaves the others untouched.
* **Course roles come from the roster**: owners and champions set what each person learns (column CourseRole of People) in
  **Team → 🧑‍🤝‍🧑 Roster and course roles**, in ✏️ Edit mode, or by uploading a roster CSV (Person, Email, CourseRole). The
  dashboard and the Course tab show that role's lessons; there is no role choice in the sidebar.
* Every table and form with a save button (edit mode, roster, owners, practices, career paths, certifications, skills,
  rhythm) only sends the changes when you press it: the page does not reload while you type.

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
`Person, Email, Role, Families, Active, Practice, CourseRole, Responsibilities` — Role = owner | champion | sme | learner;
Families = family ids separated by `;` (a learner's first family is the one they learn); Responsibilities = demand; learning.
The sidebar offers these names in **Who are you?**: your role comes with your name (managers get the **View** switch).
Up to **6 global owners** and up to 6 owners per practice (ACADEMY_MAX_OWNERS changes it): **Administration → 👑 Global
owners** and **👑 Owners of …**, with the work e-mail each one signs in with; they are saved in People with role `owner`.
A champion listed here becomes the champion of those families in the catalog (reports and notices copy them). Also the
People tab of the content workbook and ✏️ Edit mode (Team, Reports). Owners in `config/access.json` (with the optional PIN)
keep working.

## Study material (catalog/study_material.csv)
`Title, Url, Source, Category, Theme, Kind, Level, SkillId, Notes, Families` — Kind = video | playlist | search | page;
Families = the role families whose learners see it (empty = the family of its SkillId, or the whole practice). News sources
have the same `Families` column.
Shown in **Knowledge exchange → 📚 Study material** (filters by category, theme and text; each item opens the author's site)
and at the end of the **Video library** (videos play inside the app). It starts with John Savill's Technical Training
(Microsoft): 6 exact videos, his Azure Master Class, certification study crams and the themes of the practice as searches
inside his channel, and his video index. To load **every** video of his index: open https://www.azadvertizer.net/savill.html,
save it (File → Save as… → HTML) and upload it in *Study material tools*; every YouTube link becomes an item, with the
heading above it as the theme. Champions select items and **Add to the learning path** of a skill.

## The learning structure
The practice learns in this structure (one per practice; PPM and others have their own):

    Practice → Role family (lead = champion, SMEs) → Vendor → Learning path → Skill → Module → Course

| Level | Where it is kept | Key | Notes |
|---|---|---|---|
| Practice | `catalog/practices.csv` | Id | Its owners run it (Team → 🏢 Practices). |
| Role family | `catalog/skills.json` (Families sheet) | FamilyId | Champion = the family lead; SMEs come from People (Role sme). |
| Job role | `catalog/paths.json` (JobRoles sheet) | FamilyId + RoleId | sysadmin, architect… People.CourseRole takes one of them. |
| Vendor | `catalog/paths.json` (Vendors sheet) | VendorId | Short and shared by every family: MSFT, CISCO, AWS… |
| Learning path | `catalog/paths.json` (Paths sheet) | PathId | Family + vendor; CertId (e.g. AZ-900); Roles (empty = every role); Order; Active. |
| Skill | `catalog/skills.json` + placement in `paths.json` (Skills sheet: PathId, Order, Active) | SkillId | |
| Module | the Module column of each course | — | Groups the courses of a skill; empty = Core. |
| Course | `catalog/materials.json` (LearningPaths sheet), `content/families/<family>.csv` | SkillId + Url | Kind course · module · path · lab · tutorial · doc · guide · video · exam · certification · deck; Location SharePoint · Percipio · Workday MyLearning · Vendor site · Repo · Academy file · Other; Status required · optional · off. |
| Certification | Certifications tab (CSV `FamilyId, Code, Name, Vendor, Roles, Level, Url`) | FamilyId + Code | Level required · desirable · off, per job role (empty = all). |

Learners see the active learning paths of their job role, the active skills in them and the required courses (optional
ones as recommended material); the dashboard shows their next course, how many they completed and the certifications
their role asks for. The former Course tab (lessons with quizzes) was retired; the glossary, video library and ranks stay.
The first time a practice opens, `catalog/paths.json` is made from the catalog: one learning path per family and vendor.

## Each family's learning paths (champions)
In **Learning route**, the champion of a family (and owners) get **🧭 Manage the learning paths**, with tabs for **Job roles**,
**Learning paths** (vendor, certification, roles, order, active), **Skills** (which path, order, active), **Courses** and
**Certifications** (per job role; required, desirable or off). In Courses, a table of every course of the
family with **Status = required** (part of the path, counts for progress) | **optional** (recommended material) | **off**
(kept in the plan, hidden from learners), the class order, kind, provider, minutes and notes. They can upload their own
material (PowerPoint, PDF, Word, Excel, video): it becomes a class learners download. The same path is a CSV per family,
`content/families/<family-id>.csv` (`SkillId, Skill, Module, Class, Title, Url, Kind, Location, Provider, Status, Minutes, Notes`): edit it in
Excel and reopen the app (it is checked first), or download / upload it in the panel. The files, `catalog/materials.json` and
the LearningPaths tab of the content workbook always match.
