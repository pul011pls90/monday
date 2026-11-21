# Graph Report - Monday  (2026-11-21)

## Corpus Check
- Large corpus: 1306 files · ~808,456 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 2289 nodes · 6433 edges · 130 communities (87 shown, 43 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 697 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Practice Pack Generator
- SVG Diagram Generator Core
- KaTeX Parser & Macro Expander
- Student Routes & Views
- Auth & Image Storage
- Promo Video Scene Blocks
- Student Page Templates
- Legacy Promo Scenes & Brand
- Demo Seeding & Question Picker
- Core App & Exam Tests
- Data Cleanup & Core Models
- App Initialization & Packs
- Answer Grading & Question Pools
- Shared UI Macros & Public Pages
- Layout, Docs & Admin Templates
- Daily Practice & Local Dates
- App Config & Test Fixtures
- Analytics Dashboard & Queries
- Assistant Import & Review Routes
- Course Player & Seeding
- Deploy Safety & Maintenance
- Formula & Settings Tests
- Multilingual Fuzzy Search
- Question Model & App Tests
- Content Internationalization
- KaTeX Core DOM Builders
- Trigonometry Formula Block
- Attempt & Homework Tests
- Client Deploy Safety Outbox
- Promo Package Configuration
- Trig & Radical SVG Fixes
- Production Render Deployment
- Analytics Visit Tracking
- Teacher Access & Management
- Monday Weekly Test & Ranking
- Question Bank Filtering
- Formula Sheets & Exam Views
- User Auth & Google OAuth Tests
- Analytics Maintenance Jobs
- Image Audit & SVG Normalization
- Teacher Question CRUD Routes
- Skill Map & Practice Planning
- Content Tree & Work Editor
- Timed Attempt Runner & Grading
- Teacher Workspace Templates
- Admin Console Routes
- Teacher Dashboard Insights
- Bulk Question Text/JSON Importer
- KaTeX Options & Style State
- Error Reports & Access Control
- SAT Skills Roadmap API
- Results PDF Sky & Canvas
- Collections & Olympiad Sorting
- Teacher Picker & Redact Templates
- SQLAlchemy Models & Extensions
- Bank Play & Booklet Routes
- Supabase Migration & DB Config
- GitHub Keep-Awake Workflow
- Content Pack Sync & AppMeta
- Analytics Schema Migration
- Plain Math & LaTeX Converter
- Results PDF Sector Headers
- Remotion Root & Dipole Field
- Results PDF Summary Flowables
- Promo TypeScript Configuration
- Staging Render Deployment
- Results PDF Sector Aggregation
- Teacher Skill Tree Navigation
- Welcome Page Canvas Animation
- Bank Booklet Pagination
- KaTeX Math Style Metrics
- Student Profile & Onboarding
- Supabase Storage Unit Tests
- Site Status & OAuth Test Stubs
- Course Markdown HTML Renderer
- Custom Date Picker Widget
- Results PDF Builder & Fonts
- Results PDF Page Numbering
- Results PDF Hero Header
- Teacher Written Review Queue
- Home Page Sky Hero Canvas
- KaTeX Span Node Builder
- KaTeX MathML Node Builder
- Interactive Example Stepper JS
- KaTeX Settings & Trust Policy
- KaTeX Anchor Node Builder
- Student Sessions & Skills Templates
- Results PDF Pie Indicator
- App Math Preview Client JS
- Monday Sky Background Canvas
- Monday Podium & Ranking JS
- KaTeX Document Fragment Node
- KaTeX MathML Helpers
- KaTeX Symbol Node Builder
- KaTeX Path Node Builder
- Teacher Student Roster Routes
- Teacher Works Tree Grid
- Attempt Time Cap & Fix Tests
- Mistake Journal Diary Grouping
- KaTeX HTML Tree Builder
- KaTeX SVG Node Builder
- KaTeX Line Node Builder
- Master Skill Taxonomy Setup
- Interactive Visual Scenes JS
- Promo Font Licenses
- Student Context Processor
- Answer Display UI Macros
- Score Ring UI Macros
- Trigonometry Reference Templates
- More Chips UI Macro
- Progress Bar UI Macro
- Empty State UI Macro
- View Switch UI Macro

## God Nodes (most connected - your core abstractions)
1. `Question` - 118 edges
2. `User` - 109 edges
3. `Attempt` - 102 edges
4. `utcnow()` - 89 edges
5. `Work` - 83 edges
6. `ok()` - 83 edges
7. `client()` - 81 edges
8. `tpl()` - 74 edges
9. `login()` - 73 edges
10. `number()` - 67 edges

## Surprising Connections (you probably didn't know these)
- `test_ege_full_variant_combines_both_parts()` --uses--> `Work`  [INFERRED]
  tests/test_app.py → monday/models.py
- `google_callback()` --uses--> `Config`  [INFERRED]
  monday/auth.py → config.py
- `register()` --uses--> `Config`  [INFERRED]
  monday/auth.py → config.py
- `set_language()` --uses--> `Config`  [INFERRED]
  monday/auth.py → config.py
- `select_locale()` --uses--> `Config`  [INFERRED]
  monday/__init__.py → config.py

## Import Cycles
- 2-file cycle: `monday/__init__.py -> monday/course.py -> monday/__init__.py`
- 2-file cycle: `monday/__init__.py -> monday/deploy_safety.py -> monday/__init__.py`
- 2-file cycle: `monday/__init__.py -> monday/roadmap.py -> monday/__init__.py`

## Hyperedges (group relationships)
- **Admin Console Templates Suite** — monday_templates_admin_index_template, monday_templates_admin_panel_body_partial, monday_templates_admin_analytics_template, monday_templates_admin_course_builder_template, monday_templates_admin_roadmap_template, monday_templates_admin_maintenance_template [EXTRACTED 1.00]
- **Assistant Content Authoring & Bulk Import Pipeline** — monday_templates_assistant_home_template, monday_templates_assistant_preview_template, monday_templates_assistant_mine_template, monday_templates_assistant_fixes_template, monday_templates_assistant_gaps_template [EXTRACTED 1.00]
- **Deploy Safety & Maintenance Notification Flow** — docs_release_checklist_deploy_safety, docs_release_checklist_maintenance_lifecycle, monday_templates_admin_maintenance_template, monday_templates_base_deploy_safety_host [EXTRACTED 1.00]
- **Public Information & Legal Pages System** — monday_templates_info_public_layout, monday_templates_info_about_page, monday_templates_info_privacy_page, monday_templates_info_terms_page, monday_templates_partials_site_footer_template [EXTRACTED 1.00]
- **Unified Question Snapshot Rendering & Review Pipeline** — monday_templates_partials_macros_question_body, monday_templates_partials_macros_option_inputs, monday_templates_partials_macros_material, monday_templates_partials_macros_figure, monday_templates_partials_macros_written_assess, monday_templates_partials_macros_report_button, monday_templates_student_review_steps_template, monday_templates_assistant_review_template [EXTRACTED 1.00]
- **Exam & Practice Session Workspace Chrome** — monday_templates_partials_session_bar_template, monday_templates_partials_tool_panes_formula_drawer, monday_templates_partials_tool_panes_entry_rules_drawer, monday_templates_partials_tool_panes_desmos_calc_pane, monday_templates_partials_sat_reference_template [EXTRACTED 1.00]
- **Student Assessment, Mistake Journal & Remediation Loop** — monday_templates_student_attempt_template, monday_templates_student_result_template, monday_templates_student_journal_template, monday_templates_student_journal_review_template, monday_templates_student_session_template [INFERRED 0.95]
- **Question Bank Filter & Dual-View Practice Subsystem** — monday_templates_student_bank_template, monday_templates_student_bank_play_template, monday_templates_student_bank_sheet_template [EXTRACTED 1.00]
- **Student Formula Library & Inline Study Reference Ecosystem** — monday_templates_student_formulas_template, monday_templates_student_formula_template_template, monday_templates_student_course_player_template, monday_templates_student_skills_roadmap_template [INFERRED 0.85]
- **Teacher Question Picker & Bank Component Flow** — monday_templates_teacher_bank_template, monday_templates_teacher_picker_template, monday_templates_teacher_picker_tree_template, monday_templates_teacher_picker_list_template, monday_templates_teacher_picker_preview_template [INFERRED 0.95]
- **Teacher Question Editing & Redaction Workflow** — monday_templates_teacher_question_redact_template, monday_templates_teacher_question_redact_body_template, monday_templates_teacher_question_redact_inline_template, monday_templates_teacher_question_edit_template [INFERRED 0.85]
- **Student Practice Session & Skill Mastery Flow** — monday_templates_student_sessions_template, monday_templates_student_session_done_template, monday_templates_student_skills_template [INFERRED 0.85]
- **Teacher Content Authoring and Question Bank Flow** — monday_templates_teacher_tree_template, monday_templates_teacher_questions_template, monday_templates_teacher_works_template, monday_templates_teacher_work_edit_template, monday_templates_teacher_reports_template [EXTRACTED 1.00]
- **Teacher Student Roster and Homework Assessment Flow** — monday_templates_teacher_students_template, monday_templates_teacher_student_detail_template, monday_templates_teacher_review_template, monday_templates_teacher_review_detail_template, monday_templates_teacher_written_review_template [EXTRACTED 1.00]
- **Promo Site SIL OFL 1.1 Font Licenses** — promo_public_fonts_license_plex_mono_ibm_plex_mono_license, promo_public_fonts_ofl_onest_onest_font_license, promo_public_fonts_ofl_unbounded_unbounded_font_license [EXTRACTED 1.00]

## Communities (130 total, 43 thin omitted)

### Community 0 - "Practice Pack Generator"
Cohesion: 0.08
Nodes (82): _abs2(), _abs_eq2(), _af2(), _an_en(), _arcs2(), _arcs3(), _av_en(), build() (+74 more)

### Community 1 - "SVG Diagram Generator Core"
Cohesion: 0.11
Nodes (37): render(), render(), arc_path(), circle(), grid_and_axes(), line(), plot_curve(), svg_wrap() (+29 more)

### Community 2 - "KaTeX Parser & Macro Expander"
Cohesion: 0.08
Nodes (6): Cr, Hn, Mn, Nr, Vn, zn

### Community 3 - "Student Routes & Views"
Cohesion: 0.07
Nodes (43): student_required(), ladder_next(), _advance(), attempt_alive(), attempt_assess(), attempt_photo(), attempt_result(), _exam() (+35 more)

### Community 4 - "Auth & Image Storage"
Cohesion: 0.07
Nodes (28): about(), google_callback(), _google_get(), google_login(), _google_post(), _home_for(), index(), join() (+20 more)

### Community 5 - "Promo Video Scene Blocks"
Cohesion: 0.12
Nodes (41): Block1Hook(), FLOATING_SYMBOLS, LetterSpec, Point, Block2MondayTest(), COMPETITORS, OPTIONS, Block3QuestionBank() (+33 more)

### Community 6 - "Student Page Templates"
Cohesion: 0.07
Nodes (53): CSCA Official Academy Test Layout, Grid Navigation Test Layout (SAT/ENT/EGE/OGE), ORT Pages & Bubble Answer Sheet Layout, Test Attempt Runner Page, Question Bank Multi-Facet Filter Form, Question Bank Single-Question Player, Question Bank Booklet & Bubble Sheet Player, Question Bank Index & Topic Selector Page (+45 more)

### Community 7 - "Legacy Promo Scenes & Brand"
Cohesion: 0.11
Nodes (40): Caption(), LogoTile(), Cursor(), CursorKey, DotRing(), Props, Halftone(), Props (+32 more)

### Community 8 - "Demo Seeding & Question Picker"
Cohesion: 0.07
Nodes (27): build(), _exam(), _filters(), pick_random(), plan(), preview(), results(), row_data() (+19 more)

### Community 9 - "Core App & Exam Tests"
Cohesion: 0.12
Nodes (37): client(), login(), ok(), test_admin_name_platform_author_and_moderation_count(), test_admin_pages_and_moderation(), test_assistant_uploads_and_methodist_reviews(), test_bank_source_filter_and_format_info(), test_collection_test_flow() (+29 more)

### Community 10 - "Data Cleanup & Core Models"
Cohesion: 0.08
Nodes (21): _delete_works(), ensure_showcase_student(), fix_goals_and_times(), mark_pack_sources(), _once(), order_ort_monday_variants(), remove_demo_collections(), remove_demo_students() (+13 more)

### Community 11 - "App Initialization & Packs"
Cohesion: 0.07
Nodes (20): _check_schema(), _lock_supabase_api(), _register_cli(), import_pack_cmd(), migrate_analytics_cmd(), reset_db(), _register_speed(), _static_version() (+12 more)

### Community 12 - "Answer Grading & Question Pools"
Cohesion: 0.08
Nodes (25): fmt_answer(), accepted_answers(), current_monday_work(), display_answer(), exam_language(), _fits(), _get(), is_correct() (+17 more)

### Community 13 - "Shared UI Macros & Public Pages"
Cohesion: 0.08
Nodes (39): Assistant Question Review Queue Template, Pending Teacher Approval Page, Auth Welcome (Login & Registration) Page, Dev Image Audit QA Page, Dev Generated SVG Visuals QA Page, 503 Maintenance Error Page, Generic HTTP Error Page, About Monday Info Page (+31 more)

### Community 14 - "Layout, Docs & Admin Templates"
Cohesion: 0.08
Nodes (27): Exam Pack Formats (ORT, SAT, CSCA, EGE, ENT, OGE), Add Test Pack Skill Guide, Content Pack Question & Collection Schema, Monday Release Checklist (Deploy Safety), SIL OFL 1.1 License (Onest Font), SIL OFL 1.1 License (Unbounded Font), Admin Visit Analytics Dashboard (analytics.html), Admin SAT Course Lesson Builder (course_builder.html) (+19 more)

### Community 15 - "Daily Practice & Local Dates"
Cohesion: 0.09
Nodes (20): add_picks(), _allowed(), answer(), _auto_pick(), picks_for_student(), play(), _rate(), streak() (+12 more)

### Community 16 - "App Config & Test Fixtures"
Cohesion: 0.13
Nodes (15): Config, _secret_key(), _bootstrap_admin(), create_app(), StudentProfile, _make_app(), _seed_analytics_fixture(), test_analytics_apis_filters_csv_live_drawer_and_daily_job() (+7 more)

### Community 17 - "Analytics Dashboard & Queries"
Cohesion: 0.12
Nodes (20): api_live(), api_summary(), api_user_block(), api_user_detail(), api_visit_detail(), api_visits(), dashboard(), export_csv() (+12 more)

### Community 18 - "Assistant Import & Review Routes"
Cohesion: 0.11
Nodes (23): reviewer_required(), staff_required(), wrapped(), approve_all(), branch_request(), decide(), fixes(), gaps() (+15 more)

### Community 19 - "Course Player & Seeding"
Cohesion: 0.11
Nodes (19): admin_course(), _answers_match(), api_check_question(), api_complete_lesson(), build_course(), build_sat_course(), _load_topic_formulas(), _parse_num() (+11 more)

### Community 20 - "Deploy Safety & Maintenance"
Cohesion: 0.11
Nodes (17): admin_maintenance(), api_activity_complete(), api_activity_latest(), api_activity_save(), api_admin_maintenance(), _check_idempotency(), ensure_deploy_safety_tables(), get_maintenance_state() (+9 more)

### Community 21 - "Formula & Settings Tests"
Cohesion: 0.13
Nodes (27): ReferenceSheet, test_formula_sheets(), _sheet(), test_a_drawing_follows_the_formula_into_my_sheet(), test_a_sheet_shows_only_for_its_exam(), test_adding_a_formula_then_a_topic_never_doubles(), test_csca_43_formulas_and_sat_parity(), test_formulas_search_filters_and_trig_signs_svg() (+19 more)

### Community 22 - "Multilingual Fuzzy Search"
Cohesion: 0.10
Nodes (21): _allowed(), _best(), _bones(), _chunk_score(), clean(), _distance(), fold(), _glued() (+13 more)

### Community 23 - "Question Model & App Tests"
Cohesion: 0.09
Nodes (22): csca_only_fitting_questions(), Question, question_signature(), db_get_skill_parent(), test_assistant_fixes_reported_question_and_gaps(), test_big_collection_waits_for_admin(), test_content_tree_and_teacher_branches(), test_csca_pool_is_english_and_senior_school() (+14 more)

### Community 24 - "Content Internationalization"
Cohesion: 0.11
Nodes (20): _background(), work(), _chunks(), content_lang(), _fill(), _from_pattern(), _has_words(), localize() (+12 more)

### Community 25 - "KaTeX Core DOM Builders"
Cohesion: 0.09
Nodes (15): _, ct(), $e(), handler(), It(), je(), mt(), N() (+7 more)

### Community 26 - "Trigonometry Formula Block"
Cohesion: 0.11
Nodes (17): SheetEntry, build_trig_block(), dev_image_audit(), dev_visuals(), init_trig_block(), _inject(), _load_raw(), _math_tex() (+9 more)

### Community 27 - "Attempt & Homework Tests"
Cohesion: 0.12
Nodes (23): _collection_pool(), Attempt, StudentRecord, Work, db_get(), test_bank_booklet_pages_and_check(), test_collection_timer_pauses_while_away(), test_data_fixes_remove_demo_collections_and_rename_student() (+15 more)

### Community 28 - "Client Deploy Safety Outbox"
Cohesion: 0.17
Nodes (28): askConfirm(), broadcastSync(), clearUserOutbox(), collectActivitySnapshot(), enqueueSave(), ensureBannerHost(), escapeHtml(), flushOutbox() (+20 more)

### Community 29 - "Promo Package Configuration"
Cohesion: 0.08
Nodes (27): dependencies, katex@^0.16.11, react@^18.3.1, react-dom@^18.3.1, remotion@4.0.538, @remotion/cli@4.0.538, @remotion/transitions@4.0.538, description (+19 more)

### Community 30 - "Trig & Radical SVG Fixes"
Cohesion: 0.15
Nodes (21): fix_auxiliary_angle(), fix_cofunction(), fix_inverse_trig(), fix_inverse_trig_integrals(), fix_reciprocal_quotient(), fix_right_triangle(), fix_special_values(), fix_trig_integrals_log() (+13 more)

### Community 31 - "Production Render Deployment"
Cohesion: 0.07
Nodes (28): databases, databaseName, ipAllowList, name, plan, region, user, mountPath (+20 more)

### Community 32 - "Analytics Visit Tracking"
Cohesion: 0.12
Nodes (15): _detect_language(), get_client_ip(), _get_geoip_reader(), _get_or_create_cookie_id(), hash_ip(), _is_interactive_heartbeat(), _is_private_ip(), _link_active_visit_on_login() (+7 more)

### Community 33 - "Teacher Access & Management"
Cohesion: 0.15
Nodes (21): teacher_required(), new_invite_code(), temporary_password(), assignment_due(), attendance(), bank(), bank_add(), daily_remove() (+13 more)

### Community 34 - "Monday Weekly Test & Ranking"
Cohesion: 0.12
Nodes (18): local_now(), countdown_label(), monday_ranking(), mondays_left(), next_monday_test_start(), user_rank(), week_start(), _daily_block() (+10 more)

### Community 35 - "Question Bank Filtering"
Cohesion: 0.15
Nodes (16): clock(), _exam_arg(), _filters(), index(), _last_answers(), _logarithms_apart(), _match(), _matching() (+8 more)

### Community 36 - "Formula Sheets & Exam Views"
Cohesion: 0.12
Nodes (18): add_formulas(), added_ids(), all_templates(), bank_key(), exam_name(), find_template(), formulas_of(), _load_templates() (+10 more)

### Community 37 - "User Auth & Google OAuth Tests"
Cohesion: 0.09
Nodes (9): User, test_clear_recent_sessions_keeps_stats(), test_journal_update_and_monday_test(), test_mistakes_review_page(), test_profile_settings_export_and_delete(), sign_in(), test_button_shows_only_when_google_is_set_up(), test_existing_email_signs_into_that_account_and_nobody_else_gets_in() (+1 more)

### Community 38 - "Analytics Maintenance Jobs"
Cohesion: 0.12
Nodes (10): ago(), purge_old_page_views(), recalculate_user_visit_counters(), run_daily_analytics_maintenance(), start_daily_maintenance_if_due(), _worker(), _track_user(), analytics_daily_job_cmd() (+2 more)

### Community 39 - "Image Audit & SVG Normalization"
Cohesion: 0.12
Nodes (10): contrast_ratio(), parse_hex(), rel_lum(), run_audit(), static_checks(), classify_svg(), collect_inventory(), normalize_one() (+2 more)

### Community 40 - "Teacher Question CRUD Routes"
Cohesion: 0.15
Nodes (15): _after_question_save(), _allowed_image(), _fill_question(), _in_branch(), _own_question(), _parse_material(), question_delete(), question_edit() (+7 more)

### Community 41 - "Skill Map & Practice Planning"
Cohesion: 0.13
Nodes (15): AttemptAnswer, build_custom_plan(), homework_state(), mistake_breakdown(), open_mistakes(), pick_practice_questions(), progress_summary(), record_progress() (+7 more)

### Community 42 - "Content Tree & Work Editor"
Cohesion: 0.13
Nodes (11): ContentNode, _can_see_node(), _needs_review(), _new_node(), _render_editor(), _resolve_node(), _save_work(), tree_add() (+3 more)

### Community 43 - "Timed Attempt Runner & Grading"
Cohesion: 0.13
Nodes (13): current_module(), grade_version_attempt(), seconds_left(), version_layout(), answered_count(), attempt_next_module(), attempt_run(), attempt_save() (+5 more)

### Community 44 - "Teacher Workspace Templates"
Cohesion: 0.13
Nodes (22): Teacher Question Bank Template (questions.html), Teacher Error Reports Inbox Template (reports.html), Teacher Assignment Review Detail Template (review_detail.html), Teacher Homework Review Queue Template (review.html), Student Test Trend SVG, Skill Portrait, and Mistake Log, Student Knowledge, Attendance, and Standing Formula, Teacher Student Detail Profile Template (student_detail.html), Admin Active Users Directory View (admin_users_mode) (+14 more)

### Community 45 - "Admin Console Routes"
Cohesion: 0.23
Nodes (14): admin_required(), approve(), _assistant_stats(), _back(), block(), index(), _last_active(), methodist() (+6 more)

### Community 46 - "Teacher Dashboard Insights"
Cohesion: 0.14
Nodes (10): attendance_summary(), _best_by_user(), class_dots(), fresh_mistakes(), gyr(), homework_week(), monday_results(), score_trend() (+2 more)

### Community 47 - "Bulk Question Text/JSON Importer"
Cohesion: 0.22
Nodes (11): _answer_key(), _from_json(), _from_text(), guess_skill(), _letter_index(), normalize(), parse(), _set_answer() (+3 more)

### Community 49 - "Error Reports & Access Control"
Cohesion: 0.18
Nodes (7): assistant_required(), can_edit_question(), create(), handle(), inbox(), seen(), visible_reports()

### Community 50 - "SAT Skills Roadmap API"
Cohesion: 0.18
Nodes (9): RoadmapMilestone, RoadmapNode, api_checklist(), api_complete_node(), api_set_goal(), build_sat_roadmap(), _domain_diagnostic_stats(), ensure_roadmap_schema() (+1 more)

### Community 51 - "Results PDF Sky & Canvas"
Cohesion: 0.15
Nodes (5): _clouds(), _hash(), _noise(), _sky(), _smooth()

### Community 52 - "Collections & Olympiad Sorting"
Cohesion: 0.13
Nodes (9): collections(), formulas(), _natural_key(), _olympiad_grade(), _olympiad_order(), _published(), _search_works(), _sort_works() (+1 more)

### Community 53 - "Teacher Picker & Redact Templates"
Cohesion: 0.17
Nodes (16): Student Support & FAQ Template (support.html), Student Work Detail Template (work_detail.html), Teacher Account & Settings Template (account.html), Teacher Homework Assignment Template (assign.html), Teacher Question Bank & Basket Template (bank.html), Teacher Daily Dashboard Template (dashboard.html), Question Picker Split-Card List Partial (_picker_list.html), Question Picker Preview Partial (_picker_preview.html) (+8 more)

### Community 55 - "Bank Play & Booklet Routes"
Cohesion: 0.27
Nodes (12): _answer_payload(), check(), _letters(), mark(), _own_bank_attempt(), play(), reveal(), _seconds_arg() (+4 more)

### Community 56 - "Supabase Migration & DB Config"
Cohesion: 0.26
Nodes (6): _database_url(), _engine_options(), test_supabase_database_settings(), copy_database(), copy_uploads(), engine()

### Community 57 - "GitHub Keep-Awake Workflow"
Cohesion: 0.15
Nodes (12): jobs, ping, name, on, schedule, workflow_dispatch, runs-on, steps (+4 more)

### Community 58 - "Content Pack Sync & AppMeta"
Cohesion: 0.29
Nodes (6): AppMeta, _foreign_questions(), import_pack(), is_imported(), _meta_key(), sync_pack()

### Community 59 - "Analytics Schema Migration"
Cohesion: 0.26
Nodes (6): ensure_analytics_schema(), LoginEvent, PageView, _make_isolated_app(), test_analytics_migration_adds_columns_to_existing_legacy_user_table(), test_analytics_tables_columns_and_models()

### Community 60 - "Plain Math & LaTeX Converter"
Cohesion: 0.24
Nodes (9): _convert_math_chunk_to_plain(), _convert_plain_math_to_latex(), latex_to_plain(), plain_to_latex(), _repl(), _read_arg(), _read_braced(), _replace_fracs_and_roots() (+1 more)

### Community 61 - "Results PDF Sector Headers"
Cohesion: 0.18
Nodes (5): _clean(), _ring(), _sector(), SectorHead, _time()

### Community 62 - "Remotion Root & Dipole Field"
Cohesion: 0.19
Nodes (9): clamp(), DipoleField(), Props, FACES, loadFonts(), RemotionRoot(), DURATION_IN_FRAMES, FPS (+1 more)

### Community 63 - "Results PDF Summary Flowables"
Cohesion: 0.18
Nodes (3): Empty, _fit(), Tiles

### Community 64 - "Promo TypeScript Configuration"
Cohesion: 0.17
Nodes (11): compilerOptions, esModuleInterop, jsx, lib, module, moduleResolution, noEmit, skipLibCheck (+3 more)

### Community 65 - "Staging Render Deployment"
Cohesion: 0.17
Nodes (11): generateValue, key, value, services, buildCommand, envVars, name, plan (+3 more)

### Community 66 - "Results PDF Sector Aggregation"
Cohesion: 0.25
Nodes (6): group_by_sector(), is_empty(), mean_percent(), percent_of(), _summary(), test_results_grouped_by_sector()

### Community 67 - "Teacher Skill Tree Navigation"
Cohesion: 0.22
Nodes (6): visible_nodes(), _can_edit_node(), tree(), _tree_back(), tree_edit(), tree_move()

### Community 68 - "Welcome Page Canvas Animation"
Cohesion: 0.31
Nodes (7): buildMask(), drawDots(), frame(), resetLetterArrays(), resize(), setStep(), updateAxis()

### Community 69 - "Bank Booklet Pagination"
Cohesion: 0.28
Nodes (6): booklet_pages(), add(), close(), _is_compare(), _is_wide(), _plain_len()

### Community 71 - "Student Profile & Onboarding"
Cohesion: 0.25
Nodes (6): _delete_account(), _goal_for(), onboarding(), _parse_date(), _parse_int(), profile()

### Community 72 - "Supabase Storage Unit Tests"
Cohesion: 0.31
Nodes (4): FakeSupabase, test_avatar_goes_to_supabase_and_opens_through_a_signed_link(), test_pack_figures_come_from_the_repository(), with_supabase()

### Community 73 - "Site Status & OAuth Test Stubs"
Cohesion: 0.25
Nodes (4): api_site_status(), api_version(), google(), get()

### Community 74 - "Course Markdown HTML Renderer"
Cohesion: 0.36
Nodes (5): render_course_html(), flush_list(), flush_para(), flush_table(), _render_inline_md()

### Community 75 - "Custom Date Picker Widget"
Cohesion: 0.54
Nodes (7): close(), draw(), goTo(), openFor(), pick(), place(), show()

### Community 76 - "Results PDF Builder & Fonts"
Cohesion: 0.29
Nodes (3): build_results_pdf(), Overview, _register_fonts()

### Community 77 - "Results PDF Page Numbering"
Cohesion: 0.38
Nodes (5): _chrome(), _decorate(), __init__(), save(), showPage()

### Community 79 - "Teacher Written Review Queue"
Cohesion: 0.29
Nodes (5): latest_attempt(), _handed_in_empty(), review(), review_detail(), written_to_mark()

### Community 80 - "Home Page Sky Hero Canvas"
Cohesion: 0.38
Nodes (3): draw(), frame(), shuffleTiles()

### Community 83 - "Interactive Example Stepper JS"
Cohesion: 0.53
Nodes (5): drawVisual(), evalExpr(), initStepper(), niceStep(), renderLimitGraph()

### Community 86 - "Student Sessions & Skills Templates"
Cohesion: 0.33
Nodes (6): pts() Score Formatter Macro, Student Session Done Template (session_done.html), setTab() Sessions Tab Switcher, Student Sessions & Custom Builder Template (sessions.html), updateStats() Session Filter Stats Calculator, Student Skills Roadmap Template (skills.html)

### Community 88 - "App Math Preview Client JS"
Cohesion: 0.60
Nodes (3): materialBlocks(), renderMath(), updatePreview()

### Community 89 - "Monday Sky Background Canvas"
Cohesion: 0.60
Nodes (3): draw(), loop(), noise()

### Community 90 - "Monday Podium & Ranking JS"
Cohesion: 0.70
Nodes (4): render(), renderList(), renderMe(), renderPodium()

### Community 92 - "KaTeX MathML Helpers"
Cohesion: 0.40
Nodes (5): Hr(), w(), x(), qr(), v()

### Community 95 - "Teacher Student Roster Routes"
Cohesion: 0.40
Nodes (4): account(), assign(), _my_records(), students()

### Community 96 - "Teacher Works Tree Grid"
Cohesion: 0.40
Nodes (3): _work_place(), works(), _works_by_tree()

### Community 99 - "KaTeX HTML Tree Builder"
Cohesion: 0.50
Nodes (3): htmlBuilder(), r, sn()

### Community 105 - "Promo Font Licenses"
Cohesion: 0.67
Nodes (3): IBM Plex Mono Font License (SIL OFL 1.1), Onest Font License (SIL OFL 1.1), Unbounded Font License (SIL OFL 1.1)

## Knowledge Gaps
- **50 isolated node(s):** `Monday Weekly Test & Rankings`, `Trigonometry Formulas Partial (_trigonometry_block.html)`, `exam_switch Macro (layout.html)`, `Dev Image Audit QA Page`, `Generic HTTP Error Page` (+45 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 751 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **43 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Question` connect `Question Model & App Tests` to `Practice Pack Generator`, `Student Routes & Views`, `Demo Seeding & Question Picker`, `Core App & Exam Tests`, `Data Cleanup & Core Models`, `Answer Grading & Question Pools`, `Daily Practice & Local Dates`, `App Config & Test Fixtures`, `Assistant Import & Review Routes`, `Course Player & Seeding`, `Formula & Settings Tests`, `Content Internationalization`, `Attempt & Homework Tests`, `Teacher Access & Management`, `Question Bank Filtering`, `Teacher Question CRUD Routes`, `Skill Map & Practice Planning`, `Content Tree & Work Editor`, `Admin Console Routes`, `Teacher Dashboard Insights`, `Bulk Question Text/JSON Importer`, `Error Reports & Access Control`, `SQLAlchemy Models & Extensions`, `Bank Play & Booklet Routes`, `Content Pack Sync & AppMeta`, `Teacher Skill Tree Navigation`, `Supabase Storage Unit Tests`, `Teacher Student Roster Routes`, `Teacher Works Tree Grid`, `Master Skill Taxonomy Setup`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 79 inferred relationships involving `Question` (e.g. with `_assistant_stats()` and `index()`) actually correct?**
  _`Question` has 79 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Monday Weekly Test & Rankings`, `Trigonometry Formulas Partial (_trigonometry_block.html)`, `exam_switch Macro (layout.html)` to the rest of the system?**
  _50 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Practice Pack Generator` be split into smaller, more focused modules?**
  _Cohesion score 0.08171603677221655 - nodes in this community are weakly interconnected._
- **Why does `utcnow()` connect `Analytics Maintenance Jobs` to `Student Routes & Views`, `Auth & Image Storage`, `Demo Seeding & Question Picker`, `Core App & Exam Tests`, `Data Cleanup & Core Models`, `App Initialization & Packs`, `Answer Grading & Question Pools`, `Daily Practice & Local Dates`, `App Config & Test Fixtures`, `Analytics Dashboard & Queries`, `Assistant Import & Review Routes`, `Course Player & Seeding`, `Deploy Safety & Maintenance`, `Question Model & App Tests`, `Attempt & Homework Tests`, `Analytics Visit Tracking`, `Monday Weekly Test & Ranking`, `Teacher Question CRUD Routes`, `Skill Map & Practice Planning`, `Timed Attempt Runner & Grading`, `Admin Console Routes`, `Teacher Dashboard Insights`, `Error Reports & Access Control`, `SAT Skills Roadmap API`, `SQLAlchemy Models & Extensions`, `Analytics Schema Migration`, `Teacher Written Review Queue`, `Teacher Student Roster Routes`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 61 inferred relationships involving `User` (e.g. with `approve()` and `block()`) actually correct?**
  _`User` has 61 INFERRED edges - model-reasoned connections that need verification._
- **Should `SVG Diagram Generator Core` be split into smaller, more focused modules?**
  _Cohesion score 0.1080701754385965 - nodes in this community are weakly interconnected._