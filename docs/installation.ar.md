# التثبيت والبدء السريع

يتم شحن Solar AI Optimizer كصورة Docker واحدة. اختر مسار النشر الذي
يناسب بيئتك - جميع المسارات تخدم لوحة المعلومات وواجهة برمجة التطبيقات (API) على **المنفذ 8000** و
ابدأ في **وضع الظل** (للمراقبة فقط؛ لا يكتب أي عاكس حتى تقوم بالتبديل إلى الوضع المباشر).

!!! warning "وضع الظل أولاً"
يتم تعيين كل مسار افتراضيًا على **SHADOW MODE**. راقب القرارات قبل يوم أو يومين
تمكين التحكم المباشر من لوحة التحكم **التجاوزات**.

## اختر النشر الخاص بك

| الطريقة | الأفضل لـ | الثبات |
|--------|----------|-------------|
| [عامل الميناء يؤلف](#docker-compose-recommended)| Dev، homelab، مضيف Docker العام |`solar-data`المجلد |
| [عامل الميناء (صورة GHCR)](#docker-standalone-image)| حاوية واحدة، بدون إنشاء |`solar-data`المجلد |
| [تطبيق Home Assistant](#home-assistant-add-on)| HAOS / تحت الإشراف | مشرف`/data` |
| [بروكسموكس إل إكس سي](#proxmox-lxc)| Proxmox VE homelab | حجم عامل الإرساء داخل LXC |

أنظر أيضا:[إعداد مساعد المنزل](home-assistant-setup.md) · [إعدادات](configuration.md) · [`.env.example`](https://github.com/oraad/solar-ai-optimizer/blob/main/.env.example)

---

## إنشاء عامل ميناء (مستحسن) {#docker-compose-recommended}

!!! tip "يوصى به لمعظم المستخدمين"
أمر واحد، وتكوين مستمر، وترقيات سهلة. لا`.env`أو`config.yaml`مطلوب -
قم بتكوين كل شيء من لوحة التحكم **الإعدادات**.

** المتطلبات الأساسية: ** محرك Docker المزود بإصدار Compose v2.

```bash
git clone https://github.com/oraad/solar-ai-optimizer.git
cd solar-ai-optimizer
docker compose up -d --build
```

افتح **http://localhost:8000**.

لتشغيل اختبارات الواجهة الخلفية أو الواجهة الأمامية:

```bash
docker compose run --rm test
docker compose run --rm frontend-test
```

** pytest المحلي (بدون Docker): ** يتطلب **Python 3.14+** (`bash scripts/check-python.sh`).
من`backend/`، ثَبَّتَ`requirements.txt` + `requirements-dev.txt`، ثم تشغيل
`python -m pytest tests/ -q`. يطابق هذا CI عند استخدام تبعيات تطوير الريبو.
على نظام التشغيل Windows، إذا كان لديك`pytest-homeassistant-custom-component`مثبت عالميًا لـ HA
عمل مكون مخصص، يمكنه حظر مآخذ التوصيل غير المتزامنة والتسبب في ذلك`SocketBlockedError`أو
`ProactorEventLoop ... _ssock`أخطاء. هذا المشروع`pytest.ini`يعطل ذلك
البرنامج المساعد تلقائيا. يمكنك أيضًا إلغاء تثبيته أو تمريره`-p no:homeassistant`.

تدخل تجاوزات البيئة الاختيارية`docker-compose.yml` `environment:`أو`.env`ملف
(يرى[إعدادات](configuration.md)).

### تحديثات لوحة المعلومات (اختياري)

يمكن للمسؤولين التحقق من وجود إصدارات جديدة ضمن **الإعدادات → تحديثات البرامج**. تسرد اللوحة
الإصدارات المستقرة الأخيرة مع ملاحظات الإصدار المنسقة. في مضيفي التحديث الذاتي لـ Docker، اختر
**التثبيت** على أي إصدار (ترقية أو تقليله)؛ يتم إنشاء نسخة احتياطية للبيانات تلقائيًا
قبل كل تثبيت. استخدم **الاستعادة** في قسم النسخ الاحتياطية في حالة فشل التثبيت.

لتمكين **التحديثات بنقرة واحدة** من لوحة المعلومات (اسحب الصورة وأعد إنشاء الحاوية)،
استخدم تراكب التحديث الذاتي. يؤدي هذا إلى تثبيت مقبس Docker المضيف في حاوية التطبيق -
استخدم فقط على مضيفي homelab الموثوقين:

```bash
docker compose -f docker-compose.yml -f docker-compose.self-update.yml up -d
```

كل دبابيس التثبيت`SELF_UPDATE_IMAGE`إلى العلامة المحددة (على سبيل المثال.`ghcr.io/oraad/solar-ai-optimizer:0.5.8`).
لتتبع`:latest`مرة أخرى، قم بتثبيت الإصدار الأحدث من المنتقي أو قم بتعيين env var يدويًا
عند إعادة إنشاء الحاوية.

تعرض لوحة الإعدادات التقدم خطوة بخطوة (بما في ذلك سحب الصورة %). الخدمة
**غير متصل بالإنترنت لفترة وجيزة** أثناء تبديل الحاوية؛ إذا فشل الإصدار الجديد في التحقق من صحته،
تتم استعادة الحاوية السابقة تلقائيًا. عند الفشل، تحقق
`/app/data/.update-logs/latest.log`على حجم البيانات.

!!! note "نسخة الصورة"
يتطلب التثبيت بنقرة واحدة **الإصدار 0.5.5 أو أحدث** (تتضمن الصورة Docker CLI عبر
    `docker-cli`). لا يمكن تثبيت الإصدارات الأقل من الإصدار 0.5.5 عبر منتقي لوحة المعلومات.
إذا قمت بتمكين التحديث الذاتي على الإصدار 0.5.2–0.5.4، فقم بتشغيله`docker pull`وأعد إنشاء الحاوية
مرة واحدة يدويًا قبل استخدام منتقي الإصدار.

---

## عامل ميناء (صورة مستقلة) {#docker-standalone-image}

!!! info "صورة مسبقة الصنع"
استخدم هذا عندما لا تريد Docker Compose. تعمل صورة GHCR نفسها على تشغيل كل مسار نشر.

** المتطلبات الأساسية: ** محرك عامل الميناء.

سحب وتشغيل:

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest

docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -e SHADOW_MODE=true \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

البناء محلياً:

```bash
docker build -t solar-ai-optimizer .
docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

افتح **http://localhost:8000**. مستندات API: **http://localhost:8000/docs**.

بالنسبة إلى **تحديثات لوحة المعلومات بنقرة واحدة** على مضيف مستقل (بدون إنشاء)، قم بتضمين Docker
المقبس وعلامات التحديث الذاتي والفحص الصحي:

```bash
docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SHADOW_MODE=true \
  -e SELF_UPDATE_ENABLED=true \
  -e SELF_UPDATE_IMAGE=ghcr.io/oraad/solar-ai-optimizer:latest \
  --health-cmd="curl -fsS http://localhost:8000/api/health || exit 1" \
  --health-interval=30s --health-timeout=5s --health-retries=3 --health-start-period=25s \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

مخصص`docker run`لا يتم الاحتفاظ بالخيارات (وحدات التخزين الإضافية والشبكات) التي تتجاوز هذه الوصفة
عن طريق التثبيت بنقرة واحدة - استخدم الدليل`docker pull`+ إعادة إنشاء تلك الإعدادات.

---

## تطبيق Home Assistant {#home-assistant-add-on}

!!! tip "أفضل تكامل لمساعد المنزل"
لوحة الدخول الأصلية، والرمز المميز للمشرف التلقائي، ولا توجد أسلاك يدوية لعنوان URL لـ HA
عند ترك بيانات الاعتماد فارغة في خيارات التطبيق.

**المتطلبات الأساسية:** نظام التشغيل Home Assistant أو التثبيت الخاضع للإشراف مع إمكانية الوصول إلى متجر التطبيقات.

[![افتح مثيل Home Assistant واعرض مربع حوار إضافة المستودع.](https://my.home-assistant.io/badges/redirect_repository.svg)](https://my.home-assistant.io/redirect/repository/?owner=oraad&repository=solar-ai-optimizer)

1. **الإعدادات → التطبيقات → متجر التطبيقات → ⋮ → المستودعات المخصصة** → أضف:
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. قم بتثبيت **Solar AI Optimizer** من المتجر.
3. ابدأ تشغيل التطبيق وافتح **لوحة الدخول** من الشريط الجانبي لـ HA (الرمز: اللوحة الشمسية).

يسحب التطبيق الصورة الجاهزة `ghcr.io/oraad/solar-ai-optimizer` (علامة مطابقة لـ
`version` في البيان) — دون تجميع على مضيف HA. تستمر الحالة تحت `/data`
(قاعدة البيانات، تكوين وقت التشغيل، النموذج المستفاد). تعيين خيارات التطبيق لمتغيرات البيئة
عبر `run.sh` (وضع الظل، مستوى السجل، مفاتيح Solcast، رمز واجهة برمجة التطبيقات، وما إلى ذلك).

يجب أن تطابق `version` في البيان [إصدارًا منشورًا](https://github.com/oraad/solar-ai-optimizer/releases) على GHCR.

أسلاك HA الكاملة (الكيانات والحزم ومصادقة الدخول):[إعداد مساعد المنزل](home-assistant-setup.md).

---

## بروكسموكس إل إكس سي {#proxmox-lxc}

!!! info "بطانة واحدة على Proxmox VE"
يقوم المساعد على نمط البرامج النصية المجتمعية بإنشاء Debian أو Alpine LXC باستخدام Docker-in-LXC
(التداخل + keyctl)، يسحب صورة GHCR، ويكشف المنفذ 8000.

** المتطلبات الأساسية: ** مضيف Proxmox VE مع إمكانية الوصول إلى الجذر.

على **مضيف Proxmox** (Debian 13 Trixie LXC — الافتراضي):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

أو لقاعدة Alpine LXC الأصغر:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

افتح **http://&lt;lxc-ip&gt;:8000**.

التحديثات والنسخ الاحتياطية وتجاوزات الشوكة/الفرع وملاحظات OCI المستقبلية:
[نشر Proxmox](proxmox.md).

---

## قائمة مراجعة ما بعد التثبيت

بعد أي مسار نشر:

1. افتح لوحة التحكم → **الإعدادات**
2. **Connect Home Assistant** (عنوان URL + الرمز المميز طويل الأمد) - قم بالتخطي في حالة استخدام الوظيفة الإضافية مع أسلاك المشرف الافتراضية
3. قم بتعيين **خط العرض / خط الطول للموقع** و **المصفوفات الكهروضوئية** (مطلوبة للتنبؤات الشمسية)
4. قم بتعيين **كيانات القراءة/الكتابة للعاكس** في الإعدادات → خريطة كيان العاكس
5. اترك **وضع الظل** قيد التشغيل؛ تأكيد القرارات العامة تبدو معقولة
6. قم باستيراد الملف بشكل اختياري[حزمة HA آمنة من الفشل](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/)وقم بتمكين نبضات القلب في الإعدادات → Fail-safe
7. قم بالتبديل إلى التحكم **المباشر** فقط عندما تثق في المُحسِّن

الخطوات التالية:

- [دليل مستخدم لوحة القيادة](frontend-manual.md)- تجول علامة تبويب
- [الأدوار والوصول](ingress-auth.md)- المشرف مقابل المشاهد
- [إعداد مساعد المنزل](home-assistant-setup.md)— الرموز والحزم واكتشاف الكيان

---

## الوضع التجريبي (الوثائق/لقطات الشاشة فقط)

!!! danger "لا تستخدم أبدا في الإنتاج"
    `DEMO_MODE`يقوم بإدخال القياس عن بعد الاصطناعي ويبلغ HA بأنه متصل بلقطة الشاشة
وسير عمل التوثيق. لا ** لا ** تمكين على النظام الذي يتحكم في العاكس الحقيقي.

بالنسبة للمشرفين الذين يقومون بتجديد لقطات شاشة لوحة المعلومات:

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose exec solar python -m scripts.seed_demo
docker compose restart solar
docker compose --profile docs run --rm docs-screenshots npm ci   # once, or after lockfile changes
docker compose --profile docs run --rm docs-screenshots
```

يرى[دليل مستخدم لوحة المعلومات ← إعادة إنشاء لقطات الشاشة](frontend-manual.md#regenerating-screenshots).

### إعادة تعيين كلمة مرور المسؤول المحلي

عند تمكين تسجيل الدخول المحلي، قم بإعادة تعيين بيانات الاعتماد من جذر الريبو:

```bash
./scripts/reset-local-password.sh
```

يرى[الدخول والترخيص → إعادة تعيين كلمة مرور المسؤول المحلي](ingress-auth.md#reset-local-admin-password).
