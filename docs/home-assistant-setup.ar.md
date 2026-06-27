# إعداد مساعد المنزل

يتكامل Solar AI Optimizer مع Home Assistant باعتباره **تطبيقًا خارجيًا** — إنه كذلك بالفعل
**ليس** تكامل مخصص لـ HACS أو`custom_components/`منصة. يتصل المحسن
عبر REST وWebSocket، يقوم بتعيين الكيانات العاكسة من الإعدادات، ويستخدم بشكل اختياري صغير
HA **حزمة YAML** لأتمتة نبضات القلب الآمنة.

اختر مسار النشر الخاص بك:

| المسار | متى تستخدم |
|------|-------------|
| [ملحق المشرف](#supervisor-add-on)| HAOS أو خاضع للإشراف — موصى به لمعظم مستخدمي HA |
| [عامل الميناء + hass_ingress](#docker-with-hass_ingress)| حاوية مستقلة على نفس الشبكة مثل HA |
| [عامل ميناء مستقل](#standalone-docker)| مباشر`:8000`وصول؛ تسجيل دخول المشرف المحلي الاختياري |

بعد الاتصال، أكمل[رسم خرائط الكيان](#inverter-entity-discovery)واختياريا
[قم باستيراد الحزمة الآمنة من الفشل](#home-assistant-packages).

---

## رمز وصول طويل الأمد {#long-lived-access-token}

مطلوب لعمليات نشر Docker وProxmox (تستخدم الوظيفة الإضافية رمز المشرف تلقائيًا عندما تُترك الحقول فارغة).

1. في Home Assistant، افتح **ملفك الشخصي** (الصورة الرمزية السفلية اليسرى).
2. قم بالتمرير إلى **الأمان** → **رموز الوصول طويلة الأمد**.
3. انقر فوق **إنشاء رمز مميز**، وقم بتسميته (على سبيل المثال:`solar-ai-optimizer`)، وانسخ الرمز المميز على الفور — يتم عرضه مرة واحدة فقط.
4. في لوحة تحكم المحسن → **الإعدادات → اتصال Home Assistant**:
- **عنوان URL:**`http://homeassistant.local:8123`أو HA IP الخاص بك (على سبيل المثال.`http://192.168.1.10:8123`)
- **الرمز المميز:** قم بلصق الرمز المميز طويل الأمد
- **التحقق من SSL:** يتم تمكينه إذا كان HA يستخدم HTTPS بشهادة صالحة

بالنسبة إلى **الوظيفة الإضافية**، اترك عنوان URL/الرمز المميز فارغًا للاستخدام`http://supervisor/core`و`SUPERVISOR_TOKEN`.

قم بتدوير الرموز المميزة بشكل دوري وإلغاء الرموز المميزة غير المستخدمة من نفس صفحة الأمان.

---

## ملحق المشرف {#supervisor-add-on}

1. **المشرف → متجر الوظائف الإضافية → المستودعات** → أضف:
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. قم بتثبيت **Solar AI Optimizer** وابدأ تشغيله.
3. افتح **لوحة الدخول** من الشريط الجانبي لـ HA.
4. في **الإعدادات**، قم بتكوين خط العرض/خط الطول، والمصفوفات الكهروضوئية، و[الكيانات العاكسة](#inverter-entity-discovery).

يتم تعيين خيارات الوظيفة الإضافية (واجهة مستخدم المشرف) لمتغيرات البيئة عبر`run.sh`:

| خيار الوظيفة الإضافية | متغير البيئة |
|---------------|---------------------|
| `shadow_mode` | `SHADOW_MODE` |
| `log_level` | `LOG_LEVEL` |
| `ha_base_url` / `ha_token` | `HA_BASE_URL` / `HA_TOKEN` |
| `solcast_api_key` | `SOLCAST_API_KEY` |
| `api_token` | `API_TOKEN` |

يتم الوثوق بالدخول تلقائيًا عند تشغيله كوظيفة إضافية (`SUPERVISOR_TOKEN`); تعيين`TRUST_INGRESS_HEADERS=true`لعمليات نشر Docker/Proxmox الخارجية. وهذا يتيح هوية المستخدم الوكيل و`X-Frame-Options: SAMEORIGIN`للوحة الشريط الجانبي.
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

### حزمة نبضات القلب الآمنة من الفشل

انسخ حزمة المثال إلى تكوين HA الخاص بك:

```
config/packages/solar-optimizer-failsafe.yaml
```

الملف المصدر في المستودع:
[`examples/home-assistant/packages/solar-optimizer-failsafe.yaml`](https://github.com/oraad/solar-ai-optimizer/blob/main/examples/home-assistant/packages/solar-optimizer-failsafe.yaml)

تقوم الحزمة بإنشاء:

| الكيان | الغرض |
|--------|---------|
| `input_datetime.solar_optimizer_heartbeat`| الطابع الزمني لنبضات القلب (النبض بواسطة المُحسِّن) |
| `input_number.solar_optimizer_max_grid_charge_a`| أقصى تيار شحن للشبكة من أجل أتمتة آمنة من الفشل |
| `binary_sensor.solar_optimizer_healthy`| مستشعر القالب (لا معنى له في حالة نبضات القلب> 120 ثانية) |

قبل إعادة التحميل، قم بتحرير العناصر النائبة:

- `switch.YOUR_GRID_CHARGE_ENTITY`- مثل الإعدادات ← العاكس ← تمكين شحن الشبكة
- `number.YOUR_MAX_GRID_CHARGE_CURRENT`- نفس الإعدادات ← العاكس ← الحد الأقصى لتيار شحن الشبكة
- `input_number.solar_optimizer_max_grid_charge_a`**الأولي** — مطابقة الإعدادات ← شحن الشبكة ← الحد الأقصى لتيار شحن الشبكة (A)

أعد تحميل **المساعدين**، و**النماذج**، و**الأتمتة**. ثم قم بتكوين الجانب المحسن:
[مساعد المنزل آمن من الفشل](home-assistant-failsafe.md).

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
5. الفشل الآمن:`input_datetime.solar_optimizer_heartbeat`التحديثات في أدوات مطور HA (إذا تم استيراد الحزمة).

## استكشاف الأخطاء وإصلاحها

| العَرَض | ما يجب التحقق منه |
|---------|----------------|
| **ها غير متصل** | يمكن الوصول إلى عنوان URL من الحاوية؛ رمز صالح؛ يتطابق إعداد SSL مع HA |
| **بطاقات الحالة الفارغة** | قراءة الكيانات المعينة بشكل صحيح؛ الكيانات لا`unavailable`في ها |
| **لا توجد توقعات** | مجموعة خطوط الطول والعرض؛ لا`0,0` |
| **فشل الكتابة** | كتابة الكيانات المعينة؛ وضع الظل معطل؛ HA يمكن الوصول إليها |
| **المدخل 401/403** |`TRUST_INGRESS_HEADERS=true`; يتطابق عنوان URL للدخول مع اسم مضيف الحاوية |

## أدلة ذات صلة

- [تثبيت](installation.md)— عامل الميناء، الوظيفة الإضافية، Proxmox
- [مساعد المنزل آمن من الفشل](home-assistant-failsafe.md)- ضبط نبضات القلب
- [الأدوار والوصول](ingress-auth.md)- المشرف مقابل المشاهد
- [إعدادات](configuration.md)- env ​​vars والمثابرة
