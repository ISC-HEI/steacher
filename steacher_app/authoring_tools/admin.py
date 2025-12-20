from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponse

from .models import AuthoringSession, UploadedFile


class UploadedFileInline(admin.TabularInline):
    model = UploadedFile
    extra = 0
    readonly_fields = ('filename', 'content_type', 'size_bytes', 'page_count', 'uploaded_at')
    can_delete = False
    fields = ('filename', 'content_type', 'size_bytes', 'page_count', 'uploaded_at')
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AuthoringSession)
class AuthoringSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'course', 'created_by', 'status', 'module_link', 'files_count', 'created_at')
    list_filter = ('status', ('course', admin.RelatedOnlyFieldListFilter), ('created_by', admin.RelatedOnlyFieldListFilter))
    search_fields = ('course__name', 'created_by__username', 'created_by__email', 'teacher_instructions')
    readonly_fields = ('created_at', 'files_count', 'traces_count')
    ordering = ('-created_at',)
    inlines = [UploadedFileInline]
    
    fieldsets = (
        (None, {
            'fields': ('course', 'module', 'created_by', 'status')
        }),
        ('Instructions', {
            'fields': ('teacher_instructions',)
        }),
        ('Stats', {
            'fields': ('files_count', 'traces_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def module_link(self, obj):
        if not obj or not obj.module:
            return '-'
        try:
            url = reverse('admin:exercises_module_change', args=[obj.module.id])
            return format_html('<a href="{}">{}</a>', url, obj.module.name)
        except Exception:
            return str(obj.module)
    module_link.short_description = 'Module'
    module_link.admin_order_field = 'module'
    
    def files_count(self, obj):
        try:
            return obj.files.count()
        except Exception:
            return 0
    files_count.short_description = 'Files'
    
    def traces_count(self, obj):
        try:
            return obj.traces.filter(channel='content_import').count()
        except Exception:
            return 0
    traces_count.short_description = 'Conversation Messages'


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'session_link', 'filename', 'content_type', 'size_display', 'page_count', 'uploaded_at')
    list_filter = ('content_type', ('session__course', admin.RelatedOnlyFieldListFilter))
    search_fields = ('filename', 'session__course__name')
    readonly_fields = ('session', 'filename', 'content_type', 'size_bytes', 'page_count', 'uploaded_at', 'size_display')
    ordering = ('-uploaded_at',)
    actions = ['download_files']
    
    fieldsets = (
        (None, {
            'fields': ('session', 'filename', 'content_type', 'size_display', 'page_count')
        }),
        ('Timestamps', {
            'fields': ('uploaded_at',),
            'classes': ('collapse',)
        }),
    )
    
    def session_link(self, obj):
        if not obj or not obj.session:
            return '-'
        try:
            url = reverse('admin:authoring_tools_authoringsession_change', args=[obj.session.id])
            return format_html('<a href="{}">Session #{}</a>', url, obj.session.id)
        except Exception:
            return f'Session #{obj.session.id}'
    session_link.short_description = 'Session'
    session_link.admin_order_field = 'session'
    
    def size_display(self, obj):
        if not obj or not obj.size_bytes:
            return '0 bytes'
        size = obj.size_bytes
        if size < 1024:
            return f'{size} bytes'
        elif size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        else:
            return f'{size / (1024 * 1024):.1f} MB'
    size_display.short_description = 'File Size'
    
    def download_files(self, request, queryset):
        if queryset.count() == 1:
            uploaded_file = queryset.first()
            response = HttpResponse(uploaded_file.file_data, content_type=uploaded_file.content_type)
            response['Content-Disposition'] = f'attachment; filename="{uploaded_file.filename}"'
            return response
        else:
            self.message_user(request, "Please select exactly one file to download.", level='error')
    download_files.short_description = "Download selected file"
    
    def has_add_permission(self, request):
        return False
