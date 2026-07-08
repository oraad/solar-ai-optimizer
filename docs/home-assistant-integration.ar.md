# تكامل Home Assistant المخصص

يتطلب **Home Assistant Core 2026.7.0+**.

يوفّر تكامل HACS لـ Solar AI Optimizer رمز اقتران، ومراقبة فشل داخل HA، وكيان Update، وتشخيصات، وإعادة تهيئة/مصادقة، مع قائمة IQS داخلية لتكامل HACS (وليست شارة Core platinum). التفاصيل الكاملة والجداول والأمثلة في [النسخة الإنجليزية](home-assistant-integration.md).

**حالات الاستخدام:** fail-safe لشحن الشبكة عند توقف النبض، وتحديثات البرمجيات من كيان Update، وأتمتة على حساس Healthy — انظر [النسخة الإنجليزية](home-assistant-integration.md#use-cases).

**التثبيت:** أضف المستودع في HACS كـ Integration. حتى تفعيل `zip_release` بعد أول إصدار يحتوي `solar_ai_optimizer.zip`، يثبت HACS من أرشيف المستودع. بعد ذلك استخدم منتقي إصدارات HACS (إصدارات GitHub).

IndieAuth (من Solar إلى HA) اختياري في إعدادات Solar وليس شرطاً للحماية الاحتياطية.

عطّل `packages/solar-optimizer-failsafe.yaml` قبل تفعيل مراقب التكامل لتجنّب شحن الشبكة مرتين.

**الإزالة:** احذف التكامل من الإعدادات، ويمكنك حذف مجلد `custom_components/solar_ai_optimizer/` عند التثبيت اليدوي.
