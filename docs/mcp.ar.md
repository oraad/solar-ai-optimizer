# MCP (بروتوكول السياق النموذجي)

يعرض Solar AI Optimizer خيارًا اختياريًا[العملية التشاورية المتعددة الأطراف](https://modelcontextprotocol.io/)الخادم حتى يتمكن وكلاء الذكاء الاصطناعي (المؤشر، وأتمتة SDK) من قراءة حالة المحسن، واستكشاف الأخطاء وإصلاحها، وتطبيق نفس التجاوزات الآمنة مثل لوحة المعلومات.

MCP عبارة عن **طائرة تحكم جانبية** — وهي لا تحل محل حلقة التحكم في الوقت الفعلي. جميع الكتابات تمر عبر القائمة`Executor`ووضع الظل و`Override`نموذج السلامة.

## متى يتم استخدام MCP مقابل لوحة القيادة

| استخدم MCP عندما | استخدم لوحة المعلومات عندما |
|--------------|------------------------|
| تصحيح أخطاء منطق المحرك باستخدام وكيل AI | التحكم اليومي بالمشغل |
| ربط القرارات بالتاريخ من المؤشر | الرسوم البيانية المرئية وإعدادات واجهة المستخدم |
| تجاوزات البرمجة النصية مع مصادقة حاملها | HA دخول المشاهد/أدوار المشرف |

## قائمة التحقق الأمنية

- **الرمز المميز = المشرف الكامل.**`API_TOKEN`و`MCP_TOKEN`منح نفس الوصول المتغير كمسؤول محلي.
- تعيين`MCP_TOKEN`بشكل منفصل عن`API_TOKEN`حتى تتمكن من إلغاء وصول الوكيل دون كسر البرامج النصية لـ CI. يتم قبول كلا الرمزين المميزين لمصادقة REST وWebSocket؛ com.stdio`ApiBackend`يستدعي REST API مع أي رمز مميز تم تكوينه.
- جلسة`MCP_TOKEN`وحده (بدون`API_TOKEN`) ينشط بوابة المصادقة ويحمي نقاط نهاية REST.
- في عمليات النشر المستقلة، **مطلقًا** يتم التعيين`MCP_ENABLED=true`بدون`MCP_TOKEN`أو`API_TOKEN`.
- في الوظيفة الإضافية HA،`mcp_enabled`الافتراضي ل`false`. تمكين فقط على الشبكات الموثوقة.
- HTTP MCP (`/mcp`) يقبل **الحامل فقط** — ولا توجد ملفات تعريف الارتباط للدخول.
- يتطلب مفتاح القتل`confirm_kill_switch=true`(MCP) أو`confirm=true`(استراحة).
- التعامل مع مخرجات الأداة على أنها غير موثوقة (يمكن أن تحتوي أسماء الكيانات على نص يتم إدخاله بسرعة).

## إعداد المؤشر (stdio)

1. ابدأ المُحسّن:`docker compose up -d solar`
2. تعيين رمز مميز:`export SOLAR_MCP_TOKEN=your-secret`(يجب أن يتطابق`API_TOKEN`أو`MCP_TOKEN`على الحاوية)
3. انسخ [`.cursor/mcp.json.example`](../.cursor/mcp.json.example) إلى المستخدم أو تكوين MCP للمشروع وضبط المسارات.
4. أعد تشغيل المؤشر → الإعدادات → MCP → تحقق`solar-ai-optimizer`متصل.

يستخدم خادم stdio`mcp`إنشاء ملف تعريف والتحدث إلى واجهة برمجة التطبيقات قيد التشغيل على`http://host.docker.internal:8000`.

## HTTP البعيد (قابل للبث)

```yaml
environment:
  MCP_ENABLED: "true"
  MCP_TOKEN: "change-me"
  # MCP_HTTP_PATH: /mcp   # optional, default /mcp
```

يتم رفض التثبيت بشكل مستقل إذا لم يتم تكوين أي رمز مميز. قم بإنهاء TLS عند الوكيل العكسي أو عند دخول HA.

## كتالوج الأدوات

### المستوى 1 - ابدأ هنا

| أداة | الغرض |
|------|---------|
| `solar_get_status`| القياس المباشر، القرار، وضع الظل |
| `solar_explain_decision`| تتبع الطب الشرعي الكامل (المدخلات → الاستدلال → التنفيذ) |
| `solar_simulate_decision`| قرار التشغيل الجاف بدون كتابة |
| `solar_get_engine_config`| التكوين الفعال المنقح |
| `solar_apply_override`| يتقدم`Override`الحقول |
| `solar_clear_override`| مسح التجاوزات |

### المستوى 2 - التنقيب

`solar_get_forecast`, `solar_get_plan`, `solar_get_grid_stats`أدوات التاريخ،`solar_get_shed_snapshots`.

### المستوى 3 - الطفرة

`solar_trigger_cycle`, `solar_refresh_forecast`, `solar_update_config`.

## استكشاف أخطاء قواعد اللعبة وإصلاحها

1. **`solar_explain_decision`** — ابحث عن الطبقة: هل تدهورت التوقعات؟ تجاوز نشط؟ احتياطي لجنة السياسة النقدية؟ تخطي الكتابة؟
2. **`solar_get_engine_config`** — التحقق من المخازن المؤقتة الاحتياطية،`priority_order`، تمكين النظام الفرعي.
3. **`solar_get_decision_history`** + **`solar_get_telemetry_window`** - خطأ يحركه الإدخال مقابل خطأ منطقي.
4. **`solar_simulate_decision`** - اختبر فرضية التكوين دون الكتابة المباشرة.
5. إذا كانت المفاتيح المنطقية تشير إلى خطأ في القاعدة، فقم بإصلاح الكود`backend/app/engine/`.

### أمثلة عملت

**الاحتياطي مرتفع جدًا:** في التتبع، قارن`decision.reserve.solar_bridge_soc`مقابل`autonomy_floor_soc`. يفحص`inputs.forecast.degraded_reasons`و`engine.priority_weights`.

**تم تخطي الكتابة:** تحقق`execution.results[].skipped_reason`ل`shadow_mode`، HA قديمة، أو القدرة غير المعينة.

**الاحتياطي MPC:** تحقق`ops.metrics.mpc_fallbacks`و`engine.mpc_unavailable`.

## REST نقاط نهاية التصحيح

المشرف فقط (نفس البيانات الموجودة في أدوات الطب الشرعي لـ MCP):

- `GET /api/debug/trace?sections=decision,execution,engine`
- `POST /api/debug/simulate`(معدل محدود)

## متغيرات البيئة

| متغير | الافتراضي | الغرض |
|----------|---------|---------|
| `MCP_ENABLED` | `false`| قم بتثبيت HTTP Streamable على`/mcp` |
| `MCP_HTTP_PATH` | `/mcp`| مسار HTTP |
| `MCP_TOKEN` | `""`| رمز حامل الوكيل؛ يعود الى`API_TOKEN` |
| `SOLAR_API_URL` | `http://127.0.0.1:8000`| عنوان URL الأساسي لواجهة برمجة تطبيقات عميل stdio |

انظر أيضا[إعدادات](configuration.md).
