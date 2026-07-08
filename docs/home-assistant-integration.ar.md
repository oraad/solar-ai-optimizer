# تكامل Home Assistant المخصص

يتطلب **Home Assistant Core 2026.3.0+**.

يوفّر تكامل HACS لـ Solar AI Optimizer رمز اقتران، ومراقبة فشل داخل HA، وكيان Update بدل [حزمة YAML القديمة](home-assistant-failsafe.md). التفاصيل الكاملة في [النسخة الإنجليزية](home-assistant-integration.md).

IndieAuth (من Solar إلى HA) اختياري في إعدادات Solar وليس شرطاً للحماية الاحتياطية.

عطّل `packages/solar-optimizer-failsafe.yaml` قبل تفعيل مراقب التكامل لتجنّب شحن الشبكة مرتين.
