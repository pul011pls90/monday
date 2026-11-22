# Question-Bank, Session, Test, Solution, Formula & Export Inventory

Pre-Stage 4 audit covering **every** Flask route and Jinja template that serves questions, sessions, tests, solutions, formulas, or exports, along with its current access decorator and Stage 4 gating boundary.

Every gated route carries `@question_bank_access_required` (defined in [access.py](../monday/access.py)) and is verified by `test_every_question_serving_route_has_gating_decorator` in [test_question_bank_stage3.py](../tests/test_question_bank_stage3.py), which fails automatically if any new route is added without the decorator or explicit non-content classification.

---

## 1. Gated Routes (`@question_bank_access_required`)

### 1.1 Student Question Bank, Daily, Practice Sessions, Tests, Journal & Exports

| Endpoint | Methods | URL Rule | Current Access Decorators | Category |
|---|---|---|---|---|
| `bank.index` | `GET` | `/bank/` | `@question_bank_access_required`, `@student_required` | Question Bank |
| `bank.start` | `POST` | `/bank/start` | `@question_bank_access_required`, `@student_required` | Question Bank Session |
| `bank.play` | `GET` | `/bank/s/<int:attempt_id>` | `@question_bank_access_required`, `@student_required` | Question Bank Player |
| `bank.sheet` | `GET` | `/bank/s/<int:attempt_id>/sheet` | `@question_bank_access_required`, `@student_required` | Question Bank Booklet |
| `bank.check` | `POST` | `/bank/s/<int:attempt_id>/check` | `@question_bank_access_required`, `@student_required` | Question Answer & Explanation |
| `bank.reveal` | `POST` | `/bank/s/<int:attempt_id>/reveal` | `@question_bank_access_required`, `@student_required` | Solution & Explanation |
| `bank.mark` | `POST` | `/bank/mark` | `@question_bank_access_required`, `@student_required` | Question Bank State |
| `bank.time_spent` | `POST` | `/bank/time` | `@question_bank_access_required`, `@student_required` | Question Bank State |
| `daily.play` | `GET` | `/daily/` | `@question_bank_access_required`, `@student_required` | Daily Questions |
| `daily.answer` | `POST` | `/daily/<int:pick_id>/answer` | `@question_bank_access_required`, `@student_required` | Daily Answer & Explanation |
| `student.home` | `GET` | `/home` | `@question_bank_access_required`, `@student_required` | Daily Card & Mastery Overview |
| `student.skills` | `GET` | `/skills` | `@question_bank_access_required`, `@student_required` | Skill Map / Roadmap |
| `student.sessions` | `GET` | `/sessions` | `@question_bank_access_required`, `@student_required` | Sessions Overview |
| `student.start_session` | `POST` | `/sessions/start/<mode>` | `@question_bank_access_required`, `@student_required` | Session Start |
| `student.session_play` | `GET, POST` | `/sessions/<int:attempt_id>` | `@question_bank_access_required`, `@student_required` | Session Runner & Feedback |
| `student.session_done` | `GET` | `/sessions/<int:attempt_id>/done` | `@question_bank_access_required`, `@student_required` | Session Solutions Review |
| `student.session_custom` | `POST` | `/sessions/custom` | `@question_bank_access_required`, `@student_required` | Custom Session Start |
| `student.session_again` | `POST` | `/sessions/<int:attempt_id>/again` | `@question_bank_access_required`, `@student_required` | Session Replay |
| `student.session_retry` | `POST` | `/sessions/<int:attempt_id>/retry` | `@question_bank_access_required`, `@student_required` | Mistakes Practice Retry |
| `student.session_presets` | `POST` | `/sessions/presets` | `@question_bank_access_required`, `@student_required` | Custom Presets |
| `student.sessions_clear` | `POST` | `/sessions/clear` | `@question_bank_access_required`, `@student_required` | Session Draft Cleanup |
| `student.collections` | `GET` | `/collections` | `@question_bank_access_required`, `@student_required` | Test Collections |
| `student.work_detail` | `GET` | `/works/<int:work_id>` | `@question_bank_access_required`, `@student_required` | Test Overview |
| `student.start_work` | `POST` | `/works/<int:work_id>/start` | `@question_bank_access_required`, `@student_required` | Test Start |
| `student.attempt_run` | `GET, POST` | `/attempts/<int:attempt_id>` | `@question_bank_access_required`, `@student_required` | Test / Homework Player |
| `student.attempt_next_module` | `POST` | `/attempts/<int:attempt_id>/next-module` | `@question_bank_access_required`, `@student_required` | Test Module Advance |
| `student.attempt_alive` | `POST` | `/attempts/<int:attempt_id>/alive` | `@question_bank_access_required`, `@student_required` | Test Timer Heartbeat |
| `student.attempt_save` | `POST` | `/attempts/<int:attempt_id>/save` | `@question_bank_access_required`, `@student_required` | Test Draft Save |
| `student.attempt_photo` | `POST` | `/attempts/<int:attempt_id>/photo` | `@question_bank_access_required`, `@student_required` | Written Solution Upload |
| `student.attempt_assess` | `POST` | `/attempts/<int:attempt_id>/assess/<int:idx>` | `@question_bank_access_required`, `@student_required` | Written Solution Self-Score |
| `student.attempt_result` | `GET` | `/attempts/<int:attempt_id>/result` | `@question_bank_access_required`, `@student_required` | Test Solutions & Explanations |
| `student.homework` | `GET` | `/homework` | `@question_bank_access_required`, `@student_required` | Teacher Homework List (Stage 4: enrolled students only) |
| `student.homework_detail` | `GET` | `/homework/<int:assignment_id>` | `@question_bank_access_required`, `@student_required` | Homework Detail |
| `student.homework_start` | `POST` | `/homework/<int:assignment_id>/start` | `@question_bank_access_required`, `@student_required` | Homework Start |
| `student.journal` | `GET` | `/journal` | `@question_bank_access_required`, `@student_required` | Mistake Journal |
| `student.journal_review` | `GET` | `/journal/attempt/<int:attempt_id>` | `@question_bank_access_required`, `@student_required` | Journal Attempt Solutions |
| `student.journal_blank_reason` | `POST` | `/journal/attempt/<int:attempt_id>/blank-reason` | `@question_bank_access_required`, `@student_required` | Journal Metadata |
| `student.journal_practice` | `POST` | `/journal/attempt/<int:attempt_id>/practice` | `@question_bank_access_required`, `@student_required` | Practice Similar Mistakes |
| `student.journal_update` | `POST` | `/journal/<int:answer_id>` | `@question_bank_access_required`, `@student_required` | Journal Answer Tagging |
| `student.monday` | `GET` | `/monday` | `@question_bank_access_required`, `@student_required` | Weekly Monday Test |
| `student.monday_start` | `POST` | `/monday/start` | `@question_bank_access_required`, `@student_required` | Start Monday Test |
| `student.formulas` | `GET, POST` | `/formulas` | `@question_bank_access_required`, `@student_required` | Formulas & Personal Sheets |
| `student.formula_sheet_place` | `POST` | `/formulas/sheet/<int:sheet_id>/place` | `@question_bank_access_required`, `@student_required` | Formula Sheet Placement |
| `student.formula_template` | `GET` | `/formulas/t/<template_id>` | `@question_bank_access_required`, `@student_required` | Formula Pack View |
| `student.formula_add` | `POST` | `/formulas/t/<template_id>/add` | `@question_bank_access_required`, `@student_required` | Add Formula Pack |
| `student.profile_export` | `GET` | `/profile/export.csv` | `@question_bank_access_required`, `@student_required` | Progress CSV Export |
| `student.profile_export_pdf` | `GET` | `/profile/export.pdf` | `@question_bank_access_required`, `@student_required` | Progress PDF Export |
| `course.player` | `GET` | `/roadmap/<exam>/<unit_slug>/<lesson_slug>` | `@question_bank_access_required`, `@student_required` | Interactive Course Lesson & Problems |
| `course.api_check_question` | `POST` | `/api/course/check` | `@question_bank_access_required`, `@student_required` | Course Question Check |
| `course.api_complete_lesson` | `POST` | `/api/course/complete` | `@question_bank_access_required`, `@student_required` | Course Mastery Sync |
| `roadmap.api_complete_node` | `POST` | `/api/roadmap/node/<node_key>/complete` | `@question_bank_access_required`, `@student_required` | Roadmap Node Completion |
| `roadmap.api_set_goal` | `POST` | `/api/roadmap/goal` | `@question_bank_access_required`, `@student_required` | Roadmap Tier Selection |
| `roadmap.api_checklist` | `POST` | `/api/roadmap/checklist` | `@question_bank_access_required`, `@student_required` | SAT Checklist State |
| `trig_block.trig_sections` | `GET` | `/formulas/trigonometry` | `@question_bank_access_required`, `@login_required` | Trigonometry Formulas Index |
| `trig_block.trig_level` | `GET` | `/formulas/trigonometry/<level_id>` | `@question_bank_access_required`, `@login_required` | Trigonometry Topic & Examples |
| `trig_block.trig_api` | `GET` | `/api/trigonometry-formulas` | `@question_bank_access_required`, `@login_required` | Trigonometry Formulas JSON |
| `uploaded_file` | `GET` | `/uploads/<path:filename>` | `@question_bank_access_required`, `@login_required` (+ `_authorize_upload`) | Question Figures, Pack Figures & Solutions |
| `reports.create` | `POST` | `/report` | `@question_bank_access_required`, `@login_required` | Question Error Reporting |

### 1.2 Staff / Admin Question Authoring, Picker, Review & Exports

| Endpoint | Methods | URL Rule | Current Access Decorators | Category |
|---|---|---|---|---|
| `picker.results` | `GET` | `/teacher/picker/` | `@question_bank_access_required`, `@teacher_required` | Staff Question Picker |
| `picker.preview` | `GET` | `/teacher/picker/q/<int:qid>` | `@question_bank_access_required`, `@teacher_required` | Staff Question Preview |
| `picker.pick_random` | `GET` | `/teacher/picker/random` | `@question_bank_access_required`, `@teacher_required` | Staff Random Selection |
| `picker.plan` | `GET` | `/teacher/picker/plan` | `@question_bank_access_required`, `@teacher_required` | Staff Topic Plan Selection |
| `teacher.daily_remove` | `POST` | `/teacher/daily/<int:pick_id>/remove` | `@question_bank_access_required`, `@teacher_required` | Staff Daily Pick Management |
| `teacher.written_review` | `GET, POST` | `/teacher/attempts/<int:attempt_id>/written` | `@question_bank_access_required`, `@teacher_required` | Teacher Written Solution Review |
| `teacher.works` | `GET` | `/teacher/works` | `@question_bank_access_required`, `@teacher_required` | Teacher Tests List |
| `teacher.work_new` | `GET, POST` | `/teacher/works/new` | `@question_bank_access_required`, `@teacher_required` | Create Work / Test |
| `teacher.work_edit` | `GET, POST` | `/teacher/works/<int:work_id>/edit` | `@question_bank_access_required`, `@teacher_required` | Edit Work / Test |
| `teacher.work_status` | `POST` | `/teacher/works/<int:work_id>/status` | `@question_bank_access_required`, `@teacher_required` | Publish / Archive Work |
| `teacher.work_duplicate` | `POST` | `/teacher/works/<int:work_id>/duplicate` | `@question_bank_access_required`, `@teacher_required` | Duplicate Work |
| `teacher.work_delete` | `POST` | `/teacher/works/<int:work_id>/delete` | `@question_bank_access_required`, `@teacher_required` | Delete Work |
| `teacher.assign` | `GET, POST` | `/teacher/assign` | `@question_bank_access_required`, `@teacher_required` | Assign Homework |
| `teacher.review` | `GET` | `/teacher/review` | `@question_bank_access_required`, `@teacher_required` | Homework Submissions Queue |
| `teacher.review_detail` | `GET, POST` | `/teacher/review/<int:assignment_id>` | `@question_bank_access_required`, `@teacher_required` | Submission & Solutions Inspection |
| `teacher.tree` | `GET` | `/teacher/tree` | `@question_bank_access_required`, `@teacher_required` | Content Node Tree |
| `teacher.tree_move` | `POST` | `/teacher/tree/<int:node_id>/move` | `@question_bank_access_required`, `@teacher_required` | Edit Tree Hierarchy |
| `teacher.tree_add` | `POST` | `/teacher/tree/add` | `@question_bank_access_required`, `@teacher_required` | Add Tree Node |
| `teacher.tree_edit` | `POST` | `/teacher/tree/<int:node_id>/edit` | `@question_bank_access_required`, `@teacher_required` | Rename / Configure Tree Node |
| `teacher.questions` | `GET` | `/teacher/questions` | `@question_bank_access_required`, `@teacher_required` | Question Bank List |
| `teacher.bank` | `GET` | `/teacher/bank` | `@question_bank_access_required`, `@teacher_required` | Teacher Picker Bank |
| `teacher.bank_add` | `POST` | `/teacher/bank/add` | `@question_bank_access_required`, `@teacher_required` | Add Picked Questions to Work/Daily |
| `teacher.question_new` | `GET, POST` | `/teacher/questions/new` | `@question_bank_access_required`, `@staff_required` | Create Question |
| `teacher.question_edit` | `GET, POST` | `/teacher/questions/<int:question_id>/edit` | `@question_bank_access_required`, `@staff_required` | Edit Question (+ syncs public sample copy) |
| `teacher.question_redact` | `GET, POST` | `/teacher/questions/<int:question_id>/redact` | `@question_bank_access_required`, `@staff_required` | Question Correction Proposal |
| `teacher.question_delete` | `POST` | `/teacher/questions/<int:question_id>/delete` | `@question_bank_access_required`, `@staff_required` | Delete / Unpublish Question (+ deletes public copy) |
| `assistant.home` | `GET` | `/assistant/` | `@question_bank_access_required`, `@staff_required` | Assistant Import Form |
| `assistant.import_preview` | `POST` | `/assistant/import` | `@question_bank_access_required`, `@staff_required` | Assistant Bulk Parse Preview |
| `assistant.import_save` | `POST` | `/assistant/import/save` | `@question_bank_access_required`, `@staff_required` | Assistant Save Draft/Pending Questions |
| `assistant.mine` | `GET` | `/assistant/mine` | `@question_bank_access_required`, `@staff_required` | Assistant Authored Questions |
| `assistant.gaps` | `GET` | `/assistant/gaps` | `@question_bank_access_required`, `@staff_required` | Thin Topic Gaps |
| `assistant.fixes` | `GET` | `/assistant/fixes` | `@question_bank_access_required`, `@staff_required` | Question Error Reports for Assistants |
| `assistant.branch_request` | `POST` | `/assistant/branch-request` | `@question_bank_access_required`, `@staff_required` | Skill Tree Branch Request |
| `review.queue` | `GET` | `/review/questions` | `@question_bank_access_required`, `@reviewer_required` | Reviewer Moderation Queue |
| `review.decide` | `POST` | `/review/questions/<int:qid>` | `@question_bank_access_required`, `@reviewer_required` | Approve / Return Question (+ syncs public sample) |
| `review.approve_all` | `POST` | `/review/questions/approve-all` | `@question_bank_access_required`, `@reviewer_required` | Bulk Question Approval |
| `course.admin_course` | `GET, POST` | `/admin/course` | `@question_bank_access_required`, `@admin_required` | Admin Course Builder |
| `course.admin_course_preview` | `POST` | `/admin/course/preview` | `@question_bank_access_required`, `@admin_required` | Admin Course Block Preview |
| `roadmap.admin_roadmap` | `GET, POST` | `/admin/roadmap` | `@question_bank_access_required`, `@admin_required` | Admin Roadmap Editor |
| `trig_block.dev_visuals` | `GET` | `/dev/visuals` | `@question_bank_access_required`, `@admin_required` | Dev Formula Visuals Sheet |
| `analytics.export_csv` | `GET` | `/admin/analytics/export.csv` | `@question_bank_access_required`, `@admin_required` | Analytics CSV Export |

### 1.3 Intentionally Public Sample Endpoints (Sanitized Showcase Only)

| Endpoint | Methods | URL Rule | Access Rule | Constraints |
|---|---|---|---|---|
| `public_site.question_bank` | `GET` | `/question-bank` | Public when `PUBLIC_SITE_ENABLED=1` (404 when off) | Exposes only `status='published'`, `is_public_sample=True` sanitized stems (`text`, `material`, `options`, `public_image_key`); never `correct`, `explanation`, `video_url`, `rubric`, or `/uploads/` |
| `public_site.public_sample_media` | `GET` | `/question-bank/media/<key>` | Public (`@limiter.limit("120 per minute")`) | Strictly validates `^[0-9a-f]{32}\.(png\|jpg\|jpeg\|webp)$`, performs DB lookup requiring `is_public_sample=True` and `status='published'`, returns copied stem blob with `X-Content-Type-Options: nosniff` |

---

## 2. Templates Inventory (Questions, Sessions, Tests, Solutions, Formulas, Exports)

| Template Path | Purpose / Rendered Content | Rendered By |
|---|---|---|
| `monday/templates/student/home.html` | Daily questions card, score prediction, weak topics | `student.home` |
| `monday/templates/student/daily.html` | Interactive question-of-the-day player & answer check | `daily.play` |
| `monday/templates/student/bank.html` | Question bank filter tree, topic counts & launcher | `bank.index` |
| `monday/templates/student/bank_play.html` | Single-question Bluebook bank player & reveal | `bank.play` |
| `monday/templates/student/bank_sheet.html` | Multi-question booklet & bubble sheet bank player | `bank.sheet` |
| `monday/templates/student/sessions.html` | Session mode cards, weak topics & custom builder | `student.sessions` |
| `monday/templates/student/session.html` | Active session question player | `student.session_play` |
| `monday/templates/student/session_done.html` | Completed session summary & solutions review | `student.session_done` |
| `monday/templates/student/collections.html` | Practice tests & olympiad/university collections | `student.collections` |
| `monday/templates/student/work_detail.html` | Collection/test overview & start controls | `student.work_detail` |
| `monday/templates/student/attempt.html` | Full/modular test & homework runner + photo upload | `student.attempt_run` |
| `monday/templates/student/result.html` | Graded attempt breakdown, solutions & explanations | `student.attempt_result` |
| `monday/templates/student/homework.html` | Homework assignments list (teacher-enrolled students) | `student.homework` |
| `monday/templates/student/homework_detail.html` | Assignment overview & submission link | `student.homework_detail` |
| `monday/templates/student/journal.html` | Mistake journal history | `student.journal` |
| `monday/templates/student/journal_review.html` | Mistake review & question explanations | `student.journal_review` |
| `monday/templates/student/monday.html` | Weekly Monday live test view | `student.monday` |
| `monday/templates/student/skills.html` | Skill map & SAT roadmap progress wrapper | `student.skills` |
| `monday/templates/student/_skills_roadmap.html` | Interactive roadmap progress partial | Included in `student/skills.html` |
| `monday/templates/student/_course_overview.html` | SAT course units & mastery overview partial | Included in `student/skills.html` |
| `monday/templates/student/course_player.html` | Lesson articles, videos & embedded practice problems | `course.player` |
| `monday/templates/student/_review_steps.html` | Graded question step-by-step explanation partial | Included in `student/result.html`, `teacher/review_detail.html` |
| `monday/templates/student/formulas.html` | Student formula sheets & board placement | `student.formulas` |
| `monday/templates/student/formula_template.html` | Formula template sheet preview | `student.formula_template` |
| `monday/templates/student/trig_sections.html` | All-Trigonometry formula sections index | `trig_block.trig_sections` |
| `monday/templates/student/trig_topic.html` | Trigonometry topic formulas & worked examples | `trig_block.trig_level` |
| `monday/templates/student/profile.html` | Student profile + CSV/PDF export triggers | `student.profile` |
| `monday/templates/partials/macros.html` | Shared UI macros (`option_inputs`, `material`, `work_card`, `mode_card`) | Student & teacher templates (and sanitized `ui.material` on `public/question_bank.html`) |
| `monday/templates/partials/session_bar.html` | Question grid/navigation & timer bar | Session & test players |
| `monday/templates/partials/sat_reference.html` | Official SAT geometry/algebra formula modal | Test/bank players |
| `monday/templates/partials/tool_panes.html` | Desmos graphing calculator & formula drawer panes | Test/bank players |
| `monday/templates/partials/_example_stepper.html` | Worked math example stepper partial | Course/trig views |
| `monday/templates/_trigonometry_block.html` | Shared trigonometry entry card partial | `student/formulas.html` |
| `monday/templates/teacher/questions.html` | Teacher question repository browser | `teacher.questions` |
| `monday/templates/teacher/question_edit.html` | Teacher/staff question editor & stem uploader | `teacher.question_new`, `teacher.question_edit` |
| `monday/templates/teacher/question_redact.html` | Question correction proposal page | `teacher.question_redact` |
| `monday/templates/teacher/_question_redact_body.html` | Redaction form modal body | `teacher.question_redact` |
| `monday/templates/teacher/_question_redact_inline.html` | Inline question redaction partial | `teacher.question_redact` |
| `monday/templates/teacher/bank.html` | Staff question picker workspace | `teacher.bank` |
| `monday/templates/teacher/_picker.html` | Embedded picker UI in work editor & bank | `teacher.work_edit`, `teacher.bank` |
| `monday/templates/teacher/_picker_tree.html` | Picker skill tree counts | `picker.results` |
| `monday/templates/teacher/_picker_list.html` | Picker paginated question cards | `picker.results` |
| `monday/templates/teacher/_picker_preview.html` | Picker full question/answer preview | `picker.preview` |
| `monday/templates/teacher/works.html` | Teacher works / tests list | `teacher.works` |
| `monday/templates/teacher/work_edit.html` | Teacher work / test builder | `teacher.work_new`, `teacher.work_edit` |
| `monday/templates/teacher/assign.html` | Homework assignment screen | `teacher.assign` |
| `monday/templates/teacher/review.html` | Submitted homework queue | `teacher.review` |
| `monday/templates/teacher/review_detail.html` | Graded student test/homework inspection | `teacher.review_detail` |
| `monday/templates/teacher/written_review.html` | Teacher grading of uploaded written solution photos | `teacher.written_review` |
| `monday/templates/teacher/tree.html` | Topic/skill tree management | `teacher.tree` |
| `monday/templates/assistant/home.html` | Bulk test/question import workspace | `assistant.home` |
| `monday/templates/assistant/preview.html` | Parsed import questions preview | `assistant.import_preview` |
| `monday/templates/assistant/mine.html` | Assistant authored questions & moderation statuses | `assistant.mine` |
| `monday/templates/assistant/gaps.html` | Thin curriculum topic report | `assistant.gaps` |
| `monday/templates/assistant/fixes.html` | Reported question fixes workspace | `assistant.fixes` |
| `monday/templates/assistant/review.html` | Methodist/admin question approval queue | `review.queue` |
| `monday/templates/admin/course_builder.html` | Admin SAT course lesson & problem block editor | `course.admin_course` |
| `monday/templates/admin/roadmap.html` | Admin SAT roadmap editor | `roadmap.admin_roadmap` |
| `monday/templates/admin/analytics.html` | Admin analytics + CSV export link | `analytics.dashboard` |
| `monday/templates/dev/visuals.html` | QA formula/example SVGs sheet | `trig_block.dev_visuals` |
| `monday/templates/public/question_bank.html` | **Public sanitized preview only** (samples without answers/solutions) | `public_site.question_bank` |
