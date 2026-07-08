# نشر Proxmox

انشر **Solar AI Optimizer** على Proxmox VE باستخدام[مخطوطات المجتمع](https://github.com/community-scripts/ProxmoxVE)-style helper الذي ينشئ LXC (Debian أو Alpine)، ويقوم بتثبيت Docker، وتشغيل صورة GHCR المنشورة.

لمعرفة مسارات التثبيت الأخرى، راجع[تثبيت](installation.md).

## التثبيت السريع (ديبيان)

قم بالتشغيل على **مضيف Proxmox** (كجذر):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

أحكام المعالج:

- Debian 13 LXC مع **nesting** و **keyctl** (مطلوب لـ Docker-in-LXC)
- محرك Docker + البرنامج المساعد للإنشاء
- حاوية`solar-optimizer`من`ghcr.io/oraad/solar-ai-optimizer:latest`
- حجم عامل الإرساء المستمر`solar-data`شنت في`/app/data`

افتح لوحة القيادة في`http://<lxc-ip>:8000`.

**Home Assistant:** ثبّت [تكامل HACS](home-assistant-integration.md) للـ fail-safe وكيان التحديث. أنشئ رمز اقتران من إعدادات Solar ثم أضف التكامل في HA (Core 2026.3.0+).

يكتب البرنامج النصي التثبيت`/opt/solar-ai-optimizer/solar.env`مع`TRUST_INGRESS_HEADERS=true`(يثق في رؤوس ومجموعات المستخدم التي تدخل HA`X-Frame-Options: SAMEORIGIN`للوحة الشريط الجانبي) وبيانات اعتماد المسؤول المحلي التي يتم إنشاؤها تلقائيًا. تتم طباعة اسم المستخدم وكلمة المرور مرة واحدة في نهاية التثبيت - احفظهما.

## التثبيت السريع (جبال الألب)

بالنسبة لنظام التشغيل الأساسي LXC الأصغر، استخدم مساعد Alpine بدلاً من ذلك:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

أحكام معالج جبال الألب:

- Alpine 3.23 LXC (قرص بسعة 4 جيجابايت بشكل افتراضي) مع **تداخل** و**keyctl**
- محرك دوكر عبر`apk`(خدمة OpenRC،`json-file`سائق السجل)
- نفس`solar-optimizer`حاوية و`solar-data`حجم كمسار دبيان

استخدم **برنامج Alpine النصي للحصول على التحديثات** على عمليات تثبيت Alpine (ملف in-LXC`update`نقاط الأمر في البرنامج النصي المطابق تلقائيًا).

## ما بعد التثبيت

1. **احفظ كلمة مرور المسؤول المحلي** التي تظهر عند اكتمال التثبيت (اسم المستخدم الافتراضي هو`admin`). استخدامه لتسجيل الدخول في`http://<lxc-ip>:8000`عند عدم استخدام دخول HA.
2. افتح **الإعدادات** وقم بتعيين[عنوان URL لمساعد المنزل والرمز المميز طويل الأمد](home-assistant-setup.md#long-lived-access-token).
3. خريطة الكيانات العاكس، والموقع، وإعدادات البطارية.
4. اترك **SHADOW MODE** قيد التشغيل حتى تثق في القرارات (افتراضي).
5. تعيين اختياريا`API_TOKEN`في`/opt/solar-ai-optimizer/solar.env`على LXC وبنفس القيمة في **الإعدادات → أمان واجهة برمجة التطبيقات**.

إعادة تشغيل مساعد التحديث على تثبيت يحتوي بالفعل على بيانات اعتماد المسؤول المحلي **لا** يقوم بتدوير كلمة المرور. لإعادة تعيين كلمة المرور:

```bash
bash /opt/solar-ai-optimizer/reset-local-password.sh
```

يرى[الدخول والترخيص - إعادة تعيين كلمة مرور المسؤول المحلي](ingress-auth.md#reset-local-admin-password).

## تحديث

أعد تشغيل البرنامج النصي المساعد الذي استخدمته للتثبيت على الحاوية الموجودة (تدفق تحديث البرامج النصية للمجتمع).

**ديبيان LXC:**

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

** جبال الألب LXC: **

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

هذا يسحب أحدث صورة، ويعيد إنشاء`solar-optimizer`حاوية، ويحفظ`solar-data`مقدار. كما أنه يقوم بترحيل عمليات التثبيت الأقدم: if`TRUST_INGRESS_HEADERS`أو أن بيانات اعتماد المسؤول المحلي مفقودة`solar.env`، تتم إضافتها تلقائيًا وتظهر أي كلمة مرور جديدة مرة واحدة. يتم أيضًا إعادة كتابة كل عملية تحديث`/usr/bin/update`للإشارة إلى هذا المستودع (يعمل على إصلاح عمليات التثبيت القديمة التي كانت تشير إلى البرامج النصية للمجتمع).

من **داخل LXC**، يمكنك أيضًا تشغيل:

```bash
update
```

يقوم هذا الأمر بتشغيل نفس البرنامج النصي المساعد Solar (وليس البرامج النصية المجتمعية). يتم بيع الوظائف المساعدة ضمن [`proxmox/vendor/community-scripts/`](https://github.com/oraad/solar-ai-optimizer/tree/main/proxmox/vendor/community-scripts) وتم تحميله عبر`SOLAR_REPO_RAW`في وقت التشغيل.

أو قم بالتحديث يدويًا داخل LXC (بما في ذلك مقبس Docker وعلامات التحديث الذاتي لذلك
**الإعدادات ← تحديثات البرامج ← التحديث الآن** يستمر العمل):

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest
docker stop solar-optimizer && docker rm solar-optimizer
docker run -d --name solar-optimizer --restart unless-stopped \
  --env-file /opt/solar-ai-optimizer/solar.env \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SELF_UPDATE_ENABLED=true \
  -e SELF_UPDATE_ENV_FILE=/opt/solar-ai-optimizer/solar.env \
  -e SELF_UPDATE_IMAGE=ghcr.io/oraad/solar-ai-optimizer:latest \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

!!! tip "تفضل المساعد"
ال`update`يقوم الأمر أو البرنامج النصي المساعد من جانب المضيف بتشغيل نفس تدفق السحب وإعادة الإنشاء
وهو أقل عرضة للخطأ من اليدوي`docker run`.

## النسخ الاحتياطي {#backup}

قم بعمل نسخة احتياطية لوحدة تخزين Docker قبل الترقية:

```bash
docker run --rm -v solar-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/solar-data-backup.tar.gz -C /data .
```

ملفات مهمة:`solar.db`, `config.runtime.yaml`, `model.json`.

## تحديث لوحة المعلومات بنقرة واحدة

تقوم عمليات تثبيت Proxmox الجديدة بتثبيت مقبس Docker وتعيينه`SELF_UPDATE_ENABLED=true`على
`solar-optimizer`حاوية. يمكن للمسؤولين فتح **الإعدادات → تحديثات البرامج** لرؤية الإصدار
الملاحظات وانقر فوق **التحديث الآن** (نفس عملية السحب وإعادة الإنشاء مثل`update`).

!!! warning "الوصول إلى مأخذ توصيل عامل الميناء"
تصاعد`/var/run/docker.sock`يمنح الجذر الفعال على LXC. واجهة برمجة التطبيقات للتحديث هي
للمسؤول فقط، ولكن قم بتمكين هذا فقط على المضيفين الذين تثق بهم. أعد تشغيل مساعد التثبيت/التحديث
البرنامج النصي لتطبيق حامل المقبس على عمليات تثبيت LXC الأقدم.

يتطلب التحديث بنقرة واحدة **الإصدار 0.5.5 أو أحدث** (تتضمن الصورة واجهة سطر أوامر Docker عبر ملف
`docker-cli`طَرد). تم تثبيت الصور v0.5.2–0.5.4 على Debian Trixie`docker.io`، أيّ
لم يعد يوفر`/usr/bin/docker`. إذا رأيت *"Docker CLI غير متوفر في هذا
حاوية"*، اسحب **v0.5.5+** وأعد إنشاء (`update`أو الدليل`docker run`فوق).

تقوم لوحة المعلومات **التثبيت** بإعادة تسمية الحاوية قيد التشغيل، وتبدأ الصورة الجديدة، وتنتظر
`/api/health`، ويعود إلى الحاوية السابقة في حالة فشل فحص السلامة. تقدم
(الطبقات، المحاولات الصحية) تظهر ضمن **الإعدادات → تحديثات البرامج**. سجلات المساعد:
`/app/data/.update-logs/latest.log`داخل`solar-data`مقدار.

## استكشاف الأخطاء وإصلاحها

| العدد | تحقق |
|-------|--------|
| *Docker CLI غير متوفر في هذه الحاوية* (الإعدادات → تحديثات البرامج) | تم إصلاحه في **v0.5.5+** (`docker-cli`في الصورة). في الإصدار 0.5.2–0.5.4،`docker exec solar-optimizer command -v docker`فارغ حتى بعد إعادة إنشائه. يجري`update`بعد سحب الإصدار v0.5.5+، أو إعادة إنشائه باستخدام الدليل الكامل`docker run`الأعلام (المقبس +`SELF_UPDATE_*`بيئه). |
| لوحة الشريط الجانبي فارغة /`X-Frame-Options: deny` | `TRUST_INGRESS_HEADERS=true`في`/opt/solar-ai-optimizer/solar.env`; دخول`url`يجب أن أشير إلى`http://<lxc-ip>:8000`(وليس عنوان URL لـ HA الخاص بك)؛ التحديث إلى الصورة الحالية وإعادة تحميل الدخول في HA |
| لن يبدأ عامل الإرساء في LXC | احتياجات الحاويات`nesting=1`و`keyctl=1`(يتم تعيينه افتراضيًا في البرنامج النصي المساعد)؛ على جبال الألب تحقق أيضا`rc-service docker status` |
| لا يمكن الوصول إلى Home Assistant | يجب أن يقوم LXC بالتوجيه إلى HA على شبكة LAN الخاصة بك؛ استخدم HA IP بدلاً من mDNS إذا لزم الأمر |
| فشل التحقق من الصحة |`docker logs solar-optimizer`داخل LXC |
| المنفذ 8000 قيد الاستخدام | تغيير تعيين المضيف في`/opt/solar-ai-optimizer/solar.env`نشر أو تحرير`docker run`ميناء |
| **502** بعد لوحة القيادة **تثبيت** | يفحص`/app/data/.update-logs/latest.log`على`solar-data`مقدار. إذا فشل التراجع، قم بتشغيل`update`داخل LXC أو قم بإعادة إنشائه يدويًا بكامل طاقته`docker run`الأعلام (المقبس +`SELF_UPDATE_*`بيئه). |
| يبدو أن تحديث لوحة المعلومات قد انتهى ثم تعطلت الخدمة | ابق على الإعدادات حتى تكتمل قائمة الخطوات. تؤدي عمليات التحقق من الصحة الفاشلة إلى التراجع التلقائي عندما يكون ذلك ممكنًا؛ وإلا استخدم **الاستعادة** من النسخة الاحتياطية السابقة للتثبيت. |

## شوكة / فرع

أشر إلى مرجع git الخاص بك:

```bash
export SOLAR_REPO_RAW="https://raw.githubusercontent.com/you/solar-ai-optimizer/your-branch"
bash -c "$(curl -fsSL ${SOLAR_REPO_RAW}/proxmox/ct/solar-ai-optimizer.sh)"          # Debian
bash -c "$(curl -fsSL ${SOLAR_REPO_RAW}/proxmox/ct/solar-ai-optimizer-alpine.sh)"   # Alpine
```

## المستقبل: Proxmox OCI أصلي (PVE 9.1+)

يمكن لـ Proxmox VE 9.1+ تشغيل صور OCI من GHCR كتطبيق LXCs. هذه الميزة لا تزال
**معاينة التكنولوجيا** — تتطلب التحديثات إعادة إنشاء CT، ولا يوجد دعم لـ Docker Compose.

الصورة المنشورة **OCI جاهزة** (exec`ENTRYPOINT`التسميات القياسية،`VOLUME /app/data`، التكوين الذي يحركه البيئة).

الخطوات اليدوية لمستخدمي PVE 9.1+ الأوائل:

1. **التخزين ← قوالب التصوير المقطعي ← سحب من سجل OCI** —`ghcr.io/oraad/solar-ai-optimizer:latest`
2. **إنشاء CT** من هذا القالب (`--ostype unmanaged`).
3. أضف نقطة التثبيت **`mp0` → `/app/data`** (4 جيجابايت+ مستحسن).
4. في **الخيارات → البيئة**، قم بتعيين الحد الأدنى:
   - `SHADOW_MODE=true`
   - `DATA_DIR=/app/data`
   - `DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db`
5. ابدأ التصوير المقطعي وافتحه`http://<ct-ip>:8000`.

حتى ينضج دعم OCI، يعد مساعد **Docker-in-LXC** أعلاه هو مسار الإنتاج الموصى به.

## ملفات المستودع

| المسار | الدور |
|------|------|
| [`proxmox/ct/solar-ai-optimizer.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/ct/solar-ai-optimizer.sh) | البرنامج النصي المضيف — Debian LXC (افتراضي) |
| [`proxmox/ct/solar-ai-optimizer-alpine.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/ct/solar-ai-optimizer-alpine.sh) | البرنامج النصي المضيف – Alpine LXC |
| [`proxmox/install/solar-ai-optimizer-install.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/install/solar-ai-optimizer-install.sh) | يعمل داخل LXC الجديدة |
| [`proxmox/lib/solar-common.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/lib/solar-common.sh) | الصورة المشتركة/نشر المساعدين |
| [`proxmox/vendor/community-scripts/`](https://github.com/oraad/solar-ai-optimizer/tree/main/proxmox/vendor/community-scripts) | مساعدو البرامج النصية المجتمعية الموردة (مثبتة في المنبع) |

النسخة الأساسية من هذا الدليل موجودة على[موقع التوثيق](https://oraad.github.io/solar-ai-optimizer/proxmox/). يحتفظ المستودع أيضًا بـ [`proxmox/README.md`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/README.md) لتصفح GitHub.
