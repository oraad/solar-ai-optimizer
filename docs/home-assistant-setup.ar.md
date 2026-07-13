# إعداد مساعد المنزل

Solar AI Optimizer هو **تطبيق خارجي** يتصل بـ Home Assistant عبر REST
وWebSocket. لتفعيل fail-safe والتحديثات البرمجية من HA نفسه، ثبّت
**[تكامل HACS المخصص](https://oraad.github.io/solar-ai-integration/home-assistant-integration/)** (Home Assistant **2026.7+**).

ثبّت من [`oraad/solar-ai-integration`](https://github.com/oraad/solar-ai-integration) — **وليس** هذا المستودع (هذا المستودع هو تطبيق Solar / إضافة HA Apps فقط).

لا تزال [حزمة YAML الآمنة من الفشل القديمة](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/) موجودة للإعدادات الأقدم؛
فضّل التكامل وعطّل الحزمة إذا كان الاثنان سيعملان معاً.

اختر مسار النشر الخاص بك:

| المسار | متى تستخدم |
|------|-------------|
| [تطبيق المشرف](#supervisor-add-on)| HAOS أو خاضع للإشراف — موصى به لمعظم مستخدمي HA |
| [عامل الميناء + hass_ingress](#docker-with-hass_ingress)| حاوية مستقلة على نفس الشبكة مثل HA |
| [عامل ميناء مستقل](#standalone-docker)| مباشر`:8000`وصول؛ تسجيل دخول المشرف المحلي الاختياري |
| [تكامل HA المخصص](https://oraad.github.io/solar-ai-integration/home-assistant-integration/) | Fail-safe + التحديثات في HA (يتوافق مع أي من المسارات أعلاه) |

بعد الاتصال، أكمل [رسم خرائط الكيان](#inverter-entity-discovery). لـ fail-safe،
استخدم [تكامل HACS المخصص](https://oraad.github.io/solar-ai-integration/home-assistant-integration/)
(لا تشغّل [حزمة YAML القديمة](#home-assistant-packages) جنباً إلى جنب معه).

---

## ربط Solar بـ Home Assistant {#long-lived-access-token}

| النشر | كيف يصادق Solar على HA |
|------------|-------------------------------|
| **إضافة HAOS** | `SUPERVISOR_TOKEN` تلقائيًا — لا شيء للصقه |
| **مستقل (تفاعلي)** | الإعدادات → **Solar يتحكم في Home Assistant** → **IndieAuth** |
| **مستقل (بدون واجهة)** | Env `HA_BASE_URL` + `HA_TOKEN` (رمز وصول طويل الأمد) |

يتحدث تكامل HACS **إلى** Solar عبر **رمز اقتران** أو اكتشاف المشرف — وليس رمز HA طويل الأمد.
قد تستمر البرامج النصية في استخدام env `API_TOKEN` لواجهة HTTP الخاصة بـ Solar.

### `HA_TOKEN` بدون واجهة (اختياري)

1. في Home Assistant، افتح **الملف الشخصي** → **الأمان** → **رموز الوصول طويلة الأمد**.
2. أنشئ رمزًا وعيّن `HA_BASE_URL` / `HA_TOKEN` في بيئة الحاوية.
3. فضّل IndieAuth للإعدادات التفاعلية؛ ألغِ الرموز غير المستخدمة دوريًا.

بالنسبة إلى **تطبيق HA**، اترك بيانات الاعتماد فارغة — يحقن المشرف الرمز.

---

## تطبيق المشرف {#supervisor-add-on}

[![افتح مثيل Home Assistant واعرض مربع حوار إضافة مستودع التطبيق.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Foraad%2Fsolar-ai-optimizer)

1. **الإعدادات → التطبيقات → متجر التطبيقات → ⋮ → المستودعات المخصصة** → أضف:
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. قم بتثبيت **Solar AI Optimizer** وابدأ تشغيله.
3. افتح **لوحة الدخول** من الشريط الجانبي لـ HA.
4. في **الإعدادات**، قم بتكوين خط العرض/خط الطول، والمصفوفات الكهروضوئية، و[الكيانات العاكسة](#inverter-entity-discovery).

يسحب التطبيق `ghcr.io/oraad/solar-ai-optimizer` من GHCR (علامة الإصدار من البيان)؛ دون بناء على مضيف HA.

يتم تعيين خيارات التطبيق (واجهة مستخدم المشرف) لمتغيرات البيئة عبر `run.sh`:

| خيار التطبيق | متغير البيئة |
|---------------|---------------------|
| `prerelease_updates` | `ADDON_PRERELEASE_UPDATES` |
| `shadow_mode` | `SHADOW_MODE` |
| `log_level` | `LOG_LEVEL` |
| `ha_verify_ssl` | `HA_VERIFY_SSL` |
| `mcp_token` | `MCP_TOKEN` |
| `api_token` (options.json القديمة فقط) | `API_TOKEN` |

يتم الوثوق بالدخول تلقائيًا عند تشغيله كتطبيق مشرف (`SUPERVISOR_TOKEN`); تعيين `TRUST_INGRESS_HEADERS=true` لعمليات نشر Docker/Proxmox الخارجية. وهذا يتيح هوية المستخدم الوكيل و `X-Frame-Options: SAMEORIGIN` للوحة الشريط الجانبي.
يرى[الأدوار والوصول](ingress-auth.md)لسلوك المشرف مقابل سلوك المشاهد.

---

## عامل ميناء مع hass_ingress {#docker-with-hass_ingress}

يتم استخدامه عند تشغيل المحسن كحاوية منفصلة ولكن يجب على مستخدمي HA فتحه من الشريط الجانبي HA.

### 1. حاوية المحسن

مثال`docker-compose.yml`الخدمة على نفس شبكة Docker مثل Home Assistant:

```yaml
services:
  solar-ai-optimizer:
    image: ghcr.io/oraad/solar-ai-optimizer:latest
    container_name: solar-ai-optimizer
    restart: unless-stopped
    environment:
      SHADOW_MODE: "true"
      TRUST_INGRESS_HEADERS: "true"
      DATA_DIR: /app/data
      DATABASE_URL: sqlite+aiosqlite:////app/data/solar.db
      # Optional direct admin access to :8000 (keep port unpublished if ingress-only):
      # LOCAL_ADMIN_USERNAME: admin
      # LOCAL_ADMIN_PASSWORD_HASH: ...
      # SESSION_SECRET: ...
    volumes:
      - solar-data:/app/data
    networks:
      - homeassistant
    # Do not publish 8000 publicly when using ingress-only access.

networks:
  homeassistant:
    external: true   # or shared with your HA stack

volumes:
  solar-data:
```

قم بتكوين عنوان URL/الرمز المميز لـ HA في **الإعدادات** بعد البدء لأول مرة، أو تعيينه`HA_BASE_URL` / `HA_TOKEN`في`environment`.

### 2. كتلة دخول مساعد المنزل

اضف إليه`configuration.yaml`:

```yaml
ingress:
  solar_ai:
    title: Solar AI
    icon: mdi:solar-power-variant
    require_admin: false
    work_mode: ingress
    url: http://solar-ai-optimizer:8000
    headers:
      X-Remote-User-Id: $user_id
      X-Remote-User-Name: $username
      X-Remote-User-Display-Name: $user_name
```

إعادة تحميل الدخول: **أدوات المطورين → YAML → INGRESS**.

يتطلب`TRUST_INGRESS_HEADERS=true`على المُحسِّن حتى يتمكن HA من تضمين اللوحة في الشريط الجانبي (`X-Frame-Options: SAMEORIGIN`).

أنماط المصادقة الكاملة:[الأدوار والوصول](ingress-auth.md).

---

## عامل ميناء مستقل {#standalone-docker}

```bash
docker compose up -d --build
```

افتح **http://localhost:8000** مباشرة. اختياريًا، قم بتمكين تسجيل دخول المسؤول المحلي عبر
`LOCAL_ADMIN_PASSWORD_HASH`و`SESSION_SECRET`(يرى[إعدادات](configuration.md)).

قم بتعيين عنوان URL لـ HA والرمز المميز في **الإعدادات** — لا يلزم وجود غلاف دخول.

---

## حزم مساعد المنزل {#home-assistant-packages}

تتيح لك الحزم تقسيم تكوين YAML إلى ملفات ضمن`config/packages/`.

### تمكين الحزم في التكوين.yaml {#enable-packages-in-configurationyaml}

إذا لم تكن موجودة بالفعل:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

أعد تشغيل Home Assistant أو أعد تحميل التكوين الأساسي بعد إضافة هذه الكتلة.

### حزمة آمنة من الفشل (قديمة — لا تستخدم مع HACS)

فضّل [fail-safe تكامل HACS](https://oraad.github.io/solar-ai-integration/home-assistant-integration/).
لم يعد Solar يكتب مساعد نبضات قلب في HA؛ حيوية التكامل هي
`heartbeat_last_pulse` على `GET /api/health`.

حزمة YAML المثال تحت
[`examples/home-assistant/packages/solar-optimizer-failsafe.yaml`](https://github.com/oraad/solar-ai-optimizer/blob/main/examples/home-assistant/packages/solar-optimizer-failsafe.yaml)
**مهملة**. إذا كنت ما زلت تشغّلها، عطّلها عند استخدام HACS حتى لا يُطبَّق شحن الشبكة مرتين.
لن تتلقى تحديثات كيان نبضات القلب من Solar على إصدارات Solar الحالية.

---

## اكتشاف الكيان العاكس {#inverter-entity-discovery}

يستخدم المُحسِّن **خريطة كيان غير محددة للبائع** في الإعدادات → خريطة كيان العاكس.
يتم تعيين القدرات المنطقية (SOC للبطارية، والطاقة الكهروضوئية، وتمكين شحن الشبكة، وما إلى ذلك) على HA الخاص بك
معرفات الكيان عند اتصال HA، تقدم الحقول **الإكمال التلقائي** من الكيانات المباشرة.

استخدم **أدوات المطورين → الحالات** للعثور على معرفات الكيانات. الجداول أدناه هي **نقاط البداية**
- تختلف التسمية حسب إصدار التكامل وطراز الجهاز.

### قراءة أجهزة الاستشعار

| القدرة | داي / سانسينك (MSA) | فيكترون (فينوس / ها) | جروات |
|------------|----------------------|----------------------|---------|
| `pv_power` | `sensor.*_pv*_power`أو`sensor.*_solar_power` | `sensor.*_pv_power` | `sensor.*_pv_power` |
| `load_power` | `sensor.*_load_power` | `sensor.*_ac_consumption` | `sensor.*_load_power` |
| `battery_soc` | `sensor.*_battery_soc` | `sensor.*_soc` | `sensor.*_battery_soc` |
| `battery_power` | `sensor.*_battery_power` | `sensor.*_battery_power` | `sensor.*_battery_power` |
| `grid_power` | `sensor.*_grid_power` | `sensor.*_grid_power` | `sensor.*_grid_power` |
| `grid_present` | `binary_sensor.*_grid_connected` | `binary_sensor.*_ac_input` | `binary_sensor.*_grid_status` |
| `battery_temp` | `sensor.*_battery_temperature` | `sensor.*_battery_temperature` | `sensor.*_battery_temp` |

### كتابة الضوابط

| القدرة | داي / سانسينك (MSA) | فيكترون | جروات |
|------------|----------------------|---------|---------|
| `grid_charge_enable` | `switch.*_grid_charge`| خاص بالتكامل |`switch.*_grid_charge` |
| `max_grid_charge_current` | `number.*_grid_charge_current` | `number.*_max_charge_current` | `number.*_max_grid_charge` |

### سفك الأحمال {#load-shedding}

تقبل كل طبقة **كيانات مفاتيح متعددة** (مضخة حمام السباحة + السخان، مفتاح طاقة التيار المتردد، وما إلى ذلك).
يستخدم`switch.*`أو`input_boolean.*`كيانات التحكم في الطاقة.

**الكيانات المصاحبة** (المناخ، التحديد، المروحة، وما إلى ذلك) الموجودة على نفس جهاز Home Assistant هي
يتم اكتشافه تلقائيًا ويتم التقاطه عند التساقط؛ يتم استعادتها عندما الطبقة
يعود. الأجهزة التي تم إيقاف تشغيلها قبل التخلص منها** لا يتم تشغيلها أبدًا عن طريق الاستعادة.

يتم التقاط اللقطات **مرة واحدة لكل حلقة فصل أحمال** وتُحفظ حتى الاستعادة أو المسح
أو تقليم الإعدادات — دورات الفصل المتكررة بينما المفتاح مطفأ بالفعل لا تستبدل
حالة ما قبل الفصل. قد يعمل الالتقاط بينما مراقب كتابة HA قديم؛ تبقى كتابة الإيقاف
حتى يصبح HA حديثًا.

خيارات لكل طبقة:

| المجال | الغرض |
|-------|---------|
| `restore_enabled`| استعادة على SOC متى`soc >= restore_above_soc` |
| `restore_on_grid`| استعادة عند وجود الشبكة (إذا كانت العلامة العامة قيد التشغيل) |
| `state_entities`| خريطة تجاوز اختيارية لكيان الطاقة → معرفات الكيانات المصاحبة |

حذف مفتاح في`state_entities`لاكتشاف الرفاق تلقائيًا؛ تعيين`[]`للتبديل فقط.

قم بالتكوين في علامة التبويب لوحة المعلومات **فصل الأحمال**. كيانات شحن الشبكة **الكتابة** غير مطلوبة لعمليات نشر السقيفة فقط (استخدم الإعداد المسبق للسقيفة فقط في علامة التبويب هذه). لا تزال بحاجة إلى أجهزة استشعار **قراءة** عاكسة لبطارية SOC ووجود الشبكة.

يرى[دليل مستخدم لوحة المعلومات ← طبقات فصل الأحمال](frontend-manual.md#load-shedding-tiers).

### درجة الحرارة الخارجية (اختياري)

الإعدادات ← التوقعات ← درجة الحرارة ← **وحدة الاستشعار الخارجية** — أي`sensor.*`إعداد التقارير
درجة مئوية للتنبؤ بالحمل المدرك لدرجة الحرارة.

---

## قائمة التحقق

1. يظهر الشريط العلوي للوحة المعلومات **HA متصل** (غير متصل).
2. تعرض بطاقات الحالة العامة قيم SOC وPV وتحميل حية.
3. تعرض علامة التبويب "التوقعات" مخططًا مدته 48 ساعة (يتطلب خط العرض/خط الطول في الإعدادات).
4. الإكمال التلقائي لحقول كيان الإعدادات عند الكتابة (يتطلب رمزًا مميزًا صالحًا).
5. Fail-safe (HACS): يبقى مستشعر Healthy الثنائي قيد التشغيل أثناء دورة Solar؛ راجع [وثائق التكامل](https://oraad.github.io/solar-ai-integration/home-assistant-integration/).

## استكشاف الأخطاء وإصلاحها

| العَرَض | ما يجب التحقق منه |
|---------|----------------|
| **ها غير متصل** | يمكن الوصول إلى عنوان URL من الحاوية؛ رمز صالح؛ يتطابق إعداد SSL مع HA |
| **بطاقات الحالة الفارغة** | قراءة الكيانات المعينة بشكل صحيح؛ الكيانات لا`unavailable`في ها |
| **لا توجد توقعات** | مجموعة خطوط الطول والعرض؛ لا`0,0` |
| **فشل الكتابة** | كتابة الكيانات المعينة؛ وضع الظل معطل؛ HA يمكن الوصول إليها |
| **المدخل 401/403** |`TRUST_INGRESS_HEADERS=true`; يتطابق عنوان URL للدخول مع اسم مضيف الحاوية |

## أدلة ذات صلة

- [تثبيت](installation.md)— عامل الميناء، تطبيق HA، Proxmox
- [مساعد المنزل آمن من الفشل](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/) — ضبط نبضات القلب
- [الأدوار والوصول](ingress-auth.md)- المشرف مقابل المشاهد
- [إعدادات](configuration.md)- env ​​vars والمثابرة
