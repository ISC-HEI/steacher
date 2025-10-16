from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django import forms
from django.db import IntegrityError
from django.urls import path, reverse
from django.http import HttpResponse, HttpResponseForbidden
from django.utils.html import format_html, mark_safe

from .models import User
from exercises.models import CohortMembership, CourseMembership, Attempt, Trace, ChatThread, Exercise, Course
from django.contrib.contenttypes.models import ContentType


class CohortMembershipInline(admin.TabularInline):
    model = CohortMembership
    fk_name = 'user'
    extra = 0
    autocomplete_fields = ['cohort']
    fields = ('cohort', 'role', 'status', 'joined_at', 'added_by')
    readonly_fields = ('joined_at',)
    verbose_name = 'Cohort membership'
    verbose_name_plural = 'Cohort memberships'


class CourseMembershipInline(admin.TabularInline):
    model = CourseMembership
    fk_name = 'user'
    extra = 0
    autocomplete_fields = ['course']
    fields = ('course', 'role', 'joined_at', 'added_by')
    readonly_fields = ('joined_at',)
    verbose_name = 'Course membership'
    verbose_name_plural = 'Course memberships'


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "preferred_language")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        ("Activity", {"fields": ("activity_link",), "classes": ("collapse",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "preferred_language", "password1", "password2"),
            },
        ),
    )
    list_display = ("id", "username", "email", "first_name", "last_name", "preferred_language")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    inlines = [CohortMembershipInline, CourseMembershipInline]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('activity/', self.admin_site.admin_view(self.activity_view), name='accounts_user_activity'),
            path('<int:user_id>/activity/', self.admin_site.admin_view(self.activity_view), name='accounts_user_activity_for_user'),
        ]
        return custom_urls + urls

    def get_readonly_fields(self, request, obj=None):
        # Prevent any attempt to toggle staff/superuser via admin UI
        readonly = super().get_readonly_fields(request, obj) or ()
        return tuple(set(readonly) | {"is_staff", "is_superuser", "activity_link"})

    def activity_link(self, obj):
        try:
            url = reverse('admin:accounts_user_activity_for_user', args=(obj.id,))
            return format_html('<a href="{}" target="_blank">View activity</a>', url)
        except Exception:
            return ''
    activity_link.short_description = 'Activity'

    def save_formset(self, request, form, formset, change):
        try:
            instances = formset.save(commit=False)
            # Process deletions first
            for obj in getattr(formset, 'deleted_objects', []):
                try:
                    obj.delete()
                except Exception:
                    continue
            for obj in instances:
                if isinstance(obj, (CohortMembership, CourseMembership)) and not getattr(obj, 'added_by_id', None):
                    obj.added_by = request.user
                obj.save()
            formset.save_m2m()
        except IntegrityError:
            # Handle unique owner constraints on course/cohort
            raise forms.ValidationError('Only one owner is allowed per course/cohort. Demote the existing owner before assigning a new one.')

    def activity_view(self, request, user_id=None):
        if not request.user.is_staff:
            return HttpResponseForbidden('Forbidden')

        # Parameters
        limit = 200
        selected_user = None
        user_param = request.GET.get('user_id')
        if user_id:
            try:
                selected_user = User.objects.get(pk=int(user_id))
            except Exception:
                selected_user = None
        elif user_param:
            try:
                selected_user = User.objects.get(pk=int(user_param))
            except Exception:
                selected_user = None

        # Build queries
        traces_qs = Trace.objects.all().order_by('-id')[:limit]
        attempts_qs = Attempt.objects.all().order_by('-created_at')[:limit]
        threads_qs = ChatThread.objects.all().order_by('-created_at')[:limit]
        cohort_memberships_qs = CohortMembership.objects.all().order_by('-joined_at')[:limit]
        course_memberships_qs = CourseMembership.objects.all().order_by('-joined_at')[:limit]

        if selected_user is not None:
            traces_qs = Trace.objects.filter(user=selected_user).order_by('-id')[:limit]
            attempts_qs = Attempt.objects.filter(user=selected_user).order_by('-created_at')[:limit]
            threads_qs = ChatThread.objects.filter(owner=selected_user).order_by('-created_at')[:limit]
            cohort_memberships_qs = CohortMembership.objects.filter(user=selected_user).order_by('-joined_at')[:limit]
            course_memberships_qs = CourseMembership.objects.filter(user=selected_user).order_by('-joined_at')[:limit]

        # Preload content targets for traces
        ct_attempt = ContentType.objects.get_for_model(Attempt)
        ct_ch_thread = ContentType.objects.get_for_model(ChatThread)
        ct_exercise = ContentType.objects.get_for_model(Exercise)
        ct_course = ContentType.objects.get_for_model(Course)

        attempt_ids = [t.object_id for t in traces_qs if t.content_type_id == ct_attempt.id]
        chat_ids = [t.object_id for t in traces_qs if t.content_type_id == ct_ch_thread.id]
        exercise_ids = [t.object_id for t in traces_qs if t.content_type_id == ct_exercise.id]
        course_ids = [t.object_id for t in traces_qs if t.content_type_id == ct_course.id]

        attempts_map = {a.id: a for a in Attempt.objects.filter(id__in=attempt_ids).select_related('exercise__module__course')}
        chats_map = {c.id: c for c in ChatThread.objects.filter(id__in=chat_ids).select_related('course', 'owner')}
        exercises_map = {e.id: e for e in Exercise.objects.filter(id__in=exercise_ids).select_related('module__course')}
        courses_map = {c.id: c for c in Course.objects.filter(id__in=course_ids)}

        # Compose events
        events = []

        for tr in traces_qs:
            owner_detail = ''
            course_label = ''
            try:
                if tr.content_type_id == ct_attempt.id:
                    a = attempts_map.get(tr.object_id)
                    if a:
                        attempt_url = reverse('admin:exercises_attempt_change', args=(a.id,))
                        exercise = getattr(a, 'exercise', None)
                        if exercise and getattr(exercise, 'id', None):
                            ex_url = reverse('admin:exercises_exercise_change', args=(exercise.id,))
                            ex_title = getattr(exercise, 'title', '')
                            owner_detail = format_html('{} — {}',
                                format_html('<a href="{}">Attempt #{}</a>', attempt_url, a.id),
                                format_html('<a href="{}">{}</a>', ex_url, ex_title)
                            )
                        else:
                            owner_detail = format_html('<a href="{}">Attempt #{}</a>', attempt_url, a.id)
                        course_label = getattr(a.exercise.module.course, 'name', '')
                elif tr.content_type_id == ct_ch_thread.id:
                    ch = chats_map.get(tr.object_id)
                    if ch:
                        ch_url = reverse('admin:exercises_chatthread_change', args=(ch.id,))
                        owner_detail = format_html('<a href="{}">ChatThread #{}</a> — {}', ch_url, ch.id, ch.title)
                        course_label = getattr(ch.course, 'name', '')
                elif tr.content_type_id == ct_exercise.id:
                    ex = exercises_map.get(tr.object_id)
                    if ex:
                        ex_url = reverse('admin:exercises_exercise_change', args=(ex.id,))
                        owner_detail = format_html('<a href="{}">Exercise #{}</a> — {}', ex_url, ex.id, ex.title)
                        course_label = getattr(ex.module.course, 'name', '')
                elif tr.content_type_id == ct_course.id:
                    co = courses_map.get(tr.object_id)
                    if co:
                        co_url = reverse('admin:exercises_course_change', args=(co.id,))
                        owner_detail = format_html('<a href="{}">Course #{}</a> — {}', co_url, co.id, co.name)
                        course_label = co.name
            except Exception:
                pass

            detail_html = owner_detail or tr.__str__()
            detail_with_channel = format_html('channel={} | {}', tr.channel, detail_html)

            events.append({
                'ts': getattr(tr, 'created_at', None) or None,
                'type': 'Trace',
                'user': getattr(tr.user, 'username', ''),
                'detail_html': detail_with_channel,
                'course': course_label,
            })

        for a in attempts_qs.select_related('exercise__module__course', 'user'):
            course_label = ''
            try:
                course_label = getattr(a.exercise.module.course, 'name', '')
            except Exception:
                course_label = ''
            attempt_url = reverse('admin:exercises_attempt_change', args=(a.id,))
            ex = getattr(a, 'exercise', None)
            if ex and getattr(ex, 'id', None):
                ex_url = reverse('admin:exercises_exercise_change', args=(ex.id,))
                ex_title = getattr(ex, 'title', '')
                detail_html = format_html('{} — {}',
                    format_html('<a href="{}">Attempt #{}</a>', attempt_url, a.id),
                    format_html('<a href="{}">{}</a>', ex_url, ex_title)
                )
            else:
                detail_html = format_html('<a href="{}">Attempt #{}</a>', attempt_url, a.id)

            events.append({
                'ts': getattr(a, 'created_at', None) or None,
                'type': 'Attempt',
                'user': getattr(a.user, 'username', ''),
                'detail_html': detail_html,
                'course': course_label,
            })

        for ch in threads_qs.select_related('course', 'owner'):
            ch_url = reverse('admin:exercises_chatthread_change', args=(ch.id,))
            detail_html = format_html('<a href="{}">ChatThread #{}</a> — {}', ch_url, ch.id, ch.title)
            events.append({
                'ts': getattr(ch, 'created_at', None) or None,
                'type': 'ChatThread',
                'user': getattr(ch.owner, 'username', ''),
                'detail_html': detail_html,
                'course': getattr(ch.course, 'name', ''),
            })

        for cm in cohort_memberships_qs.select_related('cohort__course', 'user'):
            events.append({
                'ts': getattr(cm, 'joined_at', None) or None,
                'type': 'CohortMembership',
                'user': getattr(cm.user, 'username', ''),
                'detail_html': format_html('Joined cohort — {} as {}', getattr(cm.cohort, 'name', ''), getattr(cm, 'role', '')),
                'course': getattr(getattr(cm, 'cohort', None), 'course', None).name if getattr(getattr(cm, 'cohort', None), 'course', None) else '',
            })

        for crm in course_memberships_qs.select_related('course', 'user'):
            events.append({
                'ts': getattr(crm, 'joined_at', None) or None,
                'type': 'CourseMembership',
                'user': getattr(crm.user, 'username', ''),
                'detail_html': format_html('Course role — {}', getattr(crm, 'role', '')),
                'course': getattr(crm.course, 'name', ''),
            })

        # Sort and trim
        events.sort(key=lambda e: (e.get('ts') or 0), reverse=True)
        events = events[:limit]

        # Build simple HTML (no custom template)
        title = 'User Activity'
        user_info = f" for user {selected_user.username} (id={selected_user.id})" if selected_user else ''
        html = [
            f"<html><head><title>{title}</title></head><body>",
            f"<h1>{title}{user_info}</h1>",
            '<form method="get" style="margin-bottom: 1em;">',
            '<label>User ID:&nbsp;<input type="number" name="user_id" value="{}" style="width: 10em;"></label>&nbsp;'.format(getattr(selected_user, 'id', '') or ''),
            '<button type="submit">Go</button>',
            '&nbsp;&nbsp;<a href="{}">Clear</a>'.format(reverse('admin:accounts_user_activity')),
            '</form>',
            '<table border="1" cellpadding="6" cellspacing="0">',
            '<thead><tr><th>Time</th><th>Type</th><th>User</th><th>Course</th><th>Detail</th></tr></thead>',
            '<tbody>',
        ]
        for ev in events:
            ts = ev.get('ts')
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ts, 'strftime') and ts else ''
            detail_cell = ev.get('detail_html')
            if not isinstance(detail_cell, str):
                # SafeString from format_html is fine; cast to str
                detail_cell = str(detail_cell)
            html.append(
                '<tr>'
                f'<td>{ts_str}</td>'
                f'<td>{ev.get("type", "")}</td>'
                f'<td>{ev.get("user", "")}</td>'
                f'<td>{ev.get("course", "")}</td>'
                f'<td>{detail_cell}</td>'
                '</tr>'
            )
        html += ['</tbody></table>', '</body></html>']
        return HttpResponse('\n'.join(html))


