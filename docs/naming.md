# Domain Naming Convention: Subscriptions vs. Lesson Passes

To keep self-study question-bank monetization strictly separated from Monday Academy's classroom/online tutoring operations:

| Concept | Russian UI Label | Models & Tables | Who Uses It |
|---|---|---|---|
| **Question-Bank Subscription** | **Подписка на банк вопросов** | `SubscriptionPlan` (`subscription_plans`), `Subscription` (`bank_subscriptions`), `SubscriptionEvent` (`subscription_events`) | Self-study users practicing independently (no teacher features, no homework) |
| **School Lesson Pass / Package** | **Абонемент** | `MembershipPlan` (`membership_plans`), `StudentPass` (`student_passes`), `PaymentTransaction` (`payment_transactions`) | Enrolled Monday Academy students studying in offline/online groups with teachers |

## Access Control Boundary

In `has_question_bank_access(user)` (`monday/access.py` & `monday/subscriptions.py`):
- **Enrollment branch**: Active `GroupEnrollment`, open `TeacherAssignment`, or claimed `StudentRecord` teacher-student link grants full Monday Academy student access (including teacher-assigned homework).
- **Subscription branch**: Active or trialing `Subscription` row grants self-study question-bank access (without teacher-only homework features).
- **Grandfathering branch**: Pre-Stage-4 unlinked students receive `User.legacy_access_until` backfilled once at migration; new registrations leave it `NULL` and start on the free tier.
