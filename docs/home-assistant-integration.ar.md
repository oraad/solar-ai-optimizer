# تكامل Home Assistant المخصص

يتطلب **Home Assistant Core 2026.7.0+**.

يوفّر تكامل HACS لـ Solar AI Optimizer رمز اقتران، ومراقبة فشل داخل HA، وكيان Update، وتشخيصات، وإعادة تهيئة/مصادقة، مع قائمة IQS داخلية لتكامل HACS (وليست شارة Core platinum). التفاصيل الكاملة والجداول والأمثلة في [النسخة الإنجليزية](home-assistant-integration.md).

**مساران للتثبيت، رقمان للإصدار:** تطبيق Solar (`VERSION` / وسوم `v*`) مقابل تكامل HACS (`INTEGRATION_VERSION` / وسوم `integration-v*`). التطبيق عبر **الإعدادات → التطبيقات**؛ التكامل عبر HACS كـ **Integration** (وليس Add-on). التفاصيل في [النسخة الإنجليزية](home-assistant-integration.md).

**حالات الاستخدام:** fail-safe لشحن الشبكة عند توقف النبض، وتحديثات البرمجيات من كيان Update، وأتمتة على حساس Healthy — التفاصيل في [النسخة الإنجليزية](home-assistant-integration.md) (قسم Use cases).

**التثبيت:** أضف المستودع في HACS كـ **Integration**. يثبت HACS من `solar_ai_optimizer.zip` على إصدارات GitHub (منتقي الإصدارات؛ مستقر افتراضياً).

**استكشاف الأخطاء:** إذا ظهر أن المستودع «مستودع إضافات» وليس تكاملاً، أضفه كـ Integration أو ثبّت يدوياً من إصدار يحتوي الملف المضغوط — انظر [النسخة الإنجليزية](home-assistant-integration.md).

IndieAuth (من Solar إلى HA) اختياري في إعدادات Solar وليس شرطاً للحماية الاحتياطية.

عطّل `packages/solar-optimizer-failsafe.yaml` قبل تفعيل مراقب التكامل لتجنّب شحن الشبكة مرتين.

**الإزالة:** احذف التكامل من الإعدادات، ويمكنك حذف مجلد `custom_components/solar_ai_optimizer/` عند التثبيت اليدوي.
