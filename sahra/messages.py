"""Approved multilingual message templates (EN / AR / HI).

Every passenger-facing sentence comes from here and is filled ONLY with verified field values.
No free-text generation means the assistant cannot "invent" a gate, status or time.
"""
from . import clock

T = {
    "head_dep": {"en": "✈️ {flight} to {city}", "ar": "✈️ الرحلة {flight} إلى {city}", "hi": "✈️ उड़ान {flight} — {city}"},
    "head_arr": {"en": "🛬 {flight} from {city}", "ar": "🛬 الرحلة {flight} القادمة من {city}", "hi": "🛬 उड़ान {flight} — {city} से"},
    "frag_gate": {"en": "Gate {v}", "ar": "البوابة {v}", "hi": "गेट {v}"},
    "frag_boarding_time": {"en": "Boarding {v}", "ar": "الصعود {v}", "hi": "बोर्डिंग {v}"},
    "frag_status": {"en": "Status: {v}", "ar": "الحالة: {v}", "hi": "स्थिति: {v}"},
    "frag_est_time_DEP": {"en": "Departs {v}", "ar": "المغادرة {v}", "hi": "प्रस्थान {v}"},
    "frag_est_time_ARR": {"en": "Arrived {v}", "ar": "الوصول {v}", "hi": "आगमन {v}"},
    "frag_belt": {"en": "Bags on Belt {v}", "ar": "الأمتعة على الحزام رقم {v}", "hi": "सामान बेल्ट {v} पर"},
    "unconfirmed": {
        "en": "⚠️ The {fields} for {flight} is not confirmed yet — our live feeds don't match, so we won't guess. Please check the departure screens or ask any staff member.",
        "ar": "⚠️ {fields} للرحلة {flight} غير مؤكد بعد — مصادر البيانات المباشرة غير متطابقة، لذلك لن نخمّن. يرجى مراجعة شاشات المغادرة أو سؤال أي موظف.",
        "hi": "⚠️ उड़ान {flight} का {fields} अभी पुष्ट नहीं है — हमारे लाइव स्रोतों की जानकारी मेल नहीं खा रही, इसलिए हम अनुमान नहीं लगाएंगे। कृपया डिपार्चर स्क्रीन देखें या किसी स्टाफ सदस्य से पूछें।"},
    "staff_alerted": {"en": "Our operations team has been alerted to confirm it.", "ar": "تم إبلاغ فريق العمليات للتأكيد.",
                      "hi": "हमारी ऑपरेशंस टीम को पुष्टि के लिए सूचित कर दिया गया है।"},
    "unknown_fields": {
        "en": "ℹ️ The {fields} for {flight}: no reliable live data right now (feed missing or out of date), so we won't guess. Please check the screens or visit the information desk.",
        "ar": "ℹ️ {fields} للرحلة {flight}: لا توجد بيانات مباشرة موثوقة حالياً (المصدر مفقود أو قديم)، لذلك لن نخمّن. يرجى مراجعة الشاشات أو مكتب الاستعلامات.",
        "hi": "ℹ️ उड़ान {flight} का {fields}: अभी कोई भरोसेमंद लाइव डेटा नहीं है (स्रोत उपलब्ध नहीं या पुराना है), इसलिए हम अनुमान नहीं लगाएंगे। कृपया स्क्रीन देखें या सूचना डेस्क पर जाएँ।"},
    "data_unknown": {
        "en": "ℹ️ We don't have reliable live information for {flight} right now (feeds missing or out of date), so we won't guess a gate, status or time. Please check the departure screens or visit the information desk.",
        "ar": "ℹ️ لا تتوفر لدينا حالياً معلومات مباشرة موثوقة عن الرحلة {flight} (المصادر مفقودة أو قديمة)، لذلك لن نخمّن البوابة أو الحالة أو الوقت. يرجى مراجعة شاشات المغادرة أو مكتب الاستعلامات.",
        "hi": "ℹ️ उड़ान {flight} के लिए अभी हमारे पास भरोसेमंद लाइव जानकारी नहीं है (स्रोत उपलब्ध नहीं या पुराने हैं), इसलिए हम गेट, स्थिति या समय का अनुमान नहीं लगाएंगे। कृपया डिपार्चर स्क्रीन देखें या सूचना डेस्क पर जाएँ।"},
    "single_source_note": {
        "en": "Source: {source} feed only (updated {age} min ago) — please also check the screens.",
        "ar": "المصدر: {source} فقط (آخر تحديث قبل {age} دقيقة) — يرجى التأكد من الشاشات أيضاً.",
        "hi": "स्रोत: केवल {source} ({age} मिनट पहले अपडेट) — कृपया स्क्रीन पर भी जाँच लें।"},
    "cancelled_advice": {
        "en": "This flight is cancelled — please contact {airline} or visit the {airline} desk for rebooking.",
        "ar": "هذه الرحلة ملغاة — يرجى التواصل مع {airline} أو زيارة مكتبها لإعادة الحجز.",
        "hi": "यह उड़ान रद्द है — दोबारा बुकिंग के लिए कृपया {airline} से संपर्क करें या {airline} डेस्क पर जाएँ।"},
    "flight_not_found": {
        "en": "I couldn't find flight {flight} in today's schedule. Please check the flight number on your boarding pass.",
        "ar": "لم أجد الرحلة {flight} في جدول اليوم. يرجى التحقق من رقم الرحلة على بطاقة الصعود.",
        "hi": "आज के शेड्यूल में उड़ान {flight} नहीं मिली। कृपया अपने बोर्डिंग पास पर उड़ान नंबर जाँचें।"},
    "need_flight": {
        "en": "Which flight are you on? Please type the flight number (for example SA204) or link your booking.",
        "ar": "ما هي رحلتك؟ يرجى كتابة رقم الرحلة (مثال SA204) أو ربط حجزك.",
        "hi": "आपकी उड़ान कौन-सी है? कृपया उड़ान नंबर लिखें (जैसे SA204) या अपनी बुकिंग लिंक करें।"},
    "ask_location": {
        "en": "🚶 To work out your walking time, tell me where you are now — for example Check-in Hall, after Security, Central Plaza or Food Court.",
        "ar": "🚶 لحساب وقت المشي، أخبرني أين أنت الآن — مثلاً صالة تسجيل الوصول أو بعد التفتيش أو الساحة المركزية أو منطقة المطاعم.",
        "hi": "🚶 चलने का समय बताने के लिए बताइए कि आप अभी कहाँ हैं — जैसे चेक-इन हॉल, सिक्योरिटी के बाद, सेंट्रल प्लाज़ा या फूड कोर्ट।"},
    "walk_plan": {
        "en": "🚶 From {origin} to Gate {gate}: about {walk} min walk ({distance} m){queue}. Leave by {leave_by} to reach the gate for boarding at {boarding}.",
        "ar": "🚶 من {origin} إلى البوابة {gate}: حوالي {walk} دقيقة مشياً ({distance} م){queue}. انطلق قبل {leave_by} لتصل إلى البوابة قبل الصعود في {boarding}.",
        "hi": "🚶 {origin} से गेट {gate}: लगभग {walk} मिनट पैदल ({distance} मी){queue}। बोर्डिंग {boarding} पर है, इसलिए {leave_by} तक निकल जाएँ।"},
    "queue_known": {"en": ", plus about {q} min queue at {cp}", "ar": "، بالإضافة إلى حوالي {q} دقيقة انتظار في {cp}",
                    "hi": ", साथ में {cp} पर लगभग {q} मिनट की कतार"},
    "queue_unknown": {"en": " — the live queue time at {cp} is not available, so allow extra time",
                      "ar": " — وقت الانتظار المباشر في {cp} غير متوفر، لذا خصّص وقتاً إضافياً",
                      "hi": " — {cp} पर कतार का लाइव समय उपलब्ध नहीं है, इसलिए अतिरिक्त समय रखें"},
    "leave_now": {
        "en": "⏰ Please start walking now — Gate {gate} is about {walk} min away and boarding starts at {boarding}.",
        "ar": "⏰ يرجى التوجه الآن — البوابة {gate} على بعد حوالي {walk} دقيقة والصعود يبدأ في {boarding}.",
        "hi": "⏰ कृपया अभी चलना शुरू करें — गेट {gate} लगभग {walk} मिनट दूर है और बोर्डिंग {boarding} पर शुरू होगी।"},
    "at_risk": {
        "en": "🚨 You may not reach Gate {gate} before boarding at {boarding} (about {walk} min away). Please go now and tell the nearest staff member — the gate team has been alerted.",
        "ar": "🚨 قد لا تصل إلى البوابة {gate} قبل الصعود في {boarding} (حوالي {walk} دقيقة). يرجى التوجه فوراً وإبلاغ أقرب موظف — تم إبلاغ فريق البوابة.",
        "hi": "🚨 हो सकता है आप बोर्डिंग ({boarding}) से पहले गेट {gate} न पहुँच पाएँ (लगभग {walk} मिनट दूर)। कृपया तुरंत जाएँ और नज़दीकी स्टाफ को बताएँ — गेट टीम को सूचित कर दिया गया है।"},
    "nudge": {
        "en": "⏰ Time to go: {flight} boards at {boarding} at Gate {gate}, about {walk} min from {origin}. Please start walking now.",
        "ar": "⏰ حان وقت التوجه: صعود الرحلة {flight} في {boarding} من البوابة {gate}، على بعد حوالي {walk} دقيقة من {origin}. يرجى التوجه الآن.",
        "hi": "⏰ चलने का समय: उड़ान {flight} की बोर्डिंग {boarding} पर गेट {gate} से है, जो {origin} से लगभग {walk} मिनट दूर है। कृपया अभी चलना शुरू करें।"},
    "nudge_prm": {
        "en": " Our assistance team has been notified and can bring a buggy — reply HELP if you need it.",
        "ar": " تم إبلاغ فريق المساعدة ويمكنه توفير عربة نقل — أرسل كلمة HELP إذا احتجت إليها.",
        "hi": " हमारी सहायता टीम को सूचित किया गया है और वह बग्गी ला सकती है — ज़रूरत हो तो HELP लिखें।"},
    "bc_gate": {
        "en": "📢 Gate change: {flight} to {city} now departs from Gate {new} (was {old}). Boarding {boarding}. Please allow time to walk.",
        "ar": "📢 تغيير البوابة: الرحلة {flight} إلى {city} تغادر الآن من البوابة {new} (بدلاً من {old}). الصعود {boarding}. يرجى تخصيص وقت للمشي.",
        "hi": "📢 गेट बदला गया: उड़ान {flight} ({city}) अब गेट {new} से जाएगी (पहले {old})। बोर्डिंग {boarding}। कृपया चलने का समय रखें।"},
    "bc_delay": {
        "en": "📢 Delay: {flight} to {city} is now expected to depart at {new} (was {old}). New boarding time {boarding}. Please keep checking the screens.",
        "ar": "📢 تأخير: من المتوقع الآن أن تغادر الرحلة {flight} إلى {city} في {new} (بدلاً من {old}). وقت الصعود الجديد {boarding}. يرجى متابعة الشاشات.",
        "hi": "📢 विलंब: उड़ान {flight} ({city}) अब {new} पर प्रस्थान करेगी (पहले {old})। नया बोर्डिंग समय {boarding}। कृपया स्क्रीन देखते रहें।"},
    "bc_cancel": {
        "en": "📢 Cancellation: {flight} to {city} has been cancelled by {airline}. Please go to the {airline} desk or contact {airline} for rebooking.",
        "ar": "📢 إلغاء: ألغت {airline} الرحلة {flight} إلى {city}. يرجى التوجه إلى مكتب {airline} أو التواصل معها لإعادة الحجز.",
        "hi": "📢 रद्द: {airline} ने उड़ान {flight} ({city}) रद्द कर दी है। दोबारा बुकिंग के लिए कृपया {airline} डेस्क पर जाएँ या {airline} से संपर्क करें।"},
    "handoff_assist": {
        "en": "🧑‍🦽 I've alerted our assistance team (request {ticket}). A staff member will come to you at {where}. Please stay there, or use any blue help point.",
        "ar": "🧑‍🦽 تم إبلاغ فريق المساعدة (طلب {ticket}). سيأتي إليك أحد الموظفين في {where}. يرجى البقاء هناك أو استخدام أي نقطة مساعدة زرقاء.",
        "hi": "🧑‍🦽 हमने सहायता टीम को सूचित कर दिया है (अनुरोध {ticket})। एक स्टाफ सदस्य {where} पर आपके पास आएगा। कृपया वहीं रहें या किसी नीले हेल्प पॉइंट का उपयोग करें।"},
    "handoff_medical": {
        "en": "🚑 This sounds urgent. I've alerted the airport medical team and the duty manager (request {ticket}) for {where}. Tell the nearest staff member or press a red help point now. If someone is unconscious or not breathing, shout for help immediately.",
        "ar": "🚑 يبدو هذا عاجلاً. تم إبلاغ الفريق الطبي في المطار ومدير المناوبة (طلب {ticket}) إلى {where}. أبلغ أقرب موظف أو اضغط على أقرب نقطة مساعدة حمراء الآن. إذا كان الشخص فاقداً للوعي أو لا يتنفس، اطلب المساعدة فوراً.",
        "hi": "🚑 यह आपात स्थिति लगती है। हमने एयरपोर्ट मेडिकल टीम और ड्यूटी मैनेजर को {where} के लिए सूचित कर दिया है (अनुरोध {ticket})। अभी नज़दीकी स्टाफ को बताएँ या लाल हेल्प पॉइंट दबाएँ। अगर कोई बेहोश है या साँस नहीं ले रहा, तो तुरंत मदद के लिए पुकारें।"},
    "where_unknown": {"en": "your location (please tell staff where you are)", "ar": "موقعك (يرجى إخبار الموظفين بمكانك)",
                      "hi": "आपकी जगह (कृपया स्टाफ को बताएँ कि आप कहाँ हैं)"},
    "handoff_unknown": {
        "en": "I'm not certain I can answer that correctly, so I've passed it to the information desk team (ref {ticket}). You can also ask any staff member.",
        "ar": "لست متأكداً من قدرتي على الإجابة بدقة، لذلك أحلت سؤالك إلى فريق مكتب الاستعلامات (مرجع {ticket}). يمكنك أيضاً سؤال أي موظف.",
        "hi": "मुझे पक्का नहीं कि मैं इसका सही उत्तर दे सकूँ, इसलिए मैंने आपका प्रश्न सूचना डेस्क टीम को भेज दिया है (संदर्भ {ticket})। आप किसी भी स्टाफ सदस्य से भी पूछ सकते हैं।"},
    "refuse_visa": {
        "en": "🛂 I can't advise on visa, transit or immigration rules — they depend on your nationality and route, and only the authorities can decide. Please check the official immigration website of your destination (and any transit) country, and confirm with your airline before you travel.",
        "ar": "🛂 لا يمكنني تقديم المشورة بشأن قواعد التأشيرات أو العبور أو الهجرة — فهي تعتمد على جنسيتك ومسارك، والجهات الرسمية وحدها تقرر ذلك. يرجى مراجعة الموقع الرسمي لدائرة الهجرة في بلد الوجهة (وبلد العبور إن وجد)، والتأكد مع شركة الطيران قبل السفر.",
        "hi": "🛂 मैं वीज़ा, ट्रांज़िट या इमिग्रेशन नियमों पर सलाह नहीं दे सकता — ये आपकी नागरिकता और रूट पर निर्भर करते हैं और केवल अधिकारी ही तय कर सकते हैं। कृपया अपने गंतव्य (और ट्रांज़िट) देश की आधिकारिक इमिग्रेशन वेबसाइट देखें और यात्रा से पहले अपनी एयरलाइन से पुष्टि करें।"},
    "refuse_privacy": {
        "en": "🔒 For privacy I can't confirm whether anyone is booked on a flight, or share names, booking references or travel details. Please contact the airline directly.",
        "ar": "🔒 حفاظاً على الخصوصية، لا يمكنني تأكيد ما إذا كان أي شخص محجوزاً على رحلة، ولا مشاركة الأسماء أو أرقام الحجز أو تفاصيل السفر. يرجى التواصل مع شركة الطيران مباشرة.",
        "hi": "🔒 गोपनीयता के कारण मैं यह पुष्टि नहीं कर सकता कि कोई व्यक्ति किसी उड़ान पर बुक है, न ही नाम, बुकिंग रेफ़रेंस या यात्रा विवरण साझा कर सकता हूँ। कृपया सीधे एयरलाइन से संपर्क करें।"},
    "official_info": {
        "en": "📘 Official published guidance ({source}, last reviewed {reviewed}):\n{text}\nFor anything not covered here, please ask a security officer — I can't make exceptions or interpretations.",
        "ar": "📘 الإرشادات الرسمية المنشورة ({source}، آخر مراجعة {reviewed}):\n{text}\nلأي أمر غير مذكور هنا، يرجى سؤال موظف الأمن — لا يمكنني منح استثناءات أو تفسيرات.",
        "hi": "📘 आधिकारिक प्रकाशित मार्गदर्शन ({source}, अंतिम समीक्षा {reviewed}):\n{text}\nजो बात यहाँ शामिल नहीं है, उसके लिए कृपया सुरक्षा अधिकारी से पूछें — मैं कोई छूट या व्याख्या नहीं दे सकता।"},
    "facility_info": {"en": "ℹ️ {text}\n(Source: {source})", "ar": "ℹ️ {text}\n(المصدر: {source})", "hi": "ℹ️ {text}\n(स्रोत: {source})"},
    "no_official": {
        "en": "I don't have official published guidance on that, so I won't guess. Please ask a security officer or the information desk.",
        "ar": "لا تتوفر لدي إرشادات رسمية منشورة حول ذلك، لذلك لن أخمّن. يرجى سؤال موظف الأمن أو مكتب الاستعلامات.",
        "hi": "इस बारे में मेरे पास कोई आधिकारिक प्रकाशित मार्गदर्शन नहीं है, इसलिए मैं अनुमान नहीं लगाऊँगा। कृपया सुरक्षा अधिकारी या सूचना डेस्क से पूछें।"},
    "lost_logged": {
        "en": "📦 Your lost-item report is logged (ref {ref}). {match} Lost & Found is near the Arrivals Hall exit and open 24/7 — keep your reference.",
        "ar": "📦 تم تسجيل بلاغك عن المفقودات (مرجع {ref}). {match} مكتب المفقودات بجوار مخرج صالة الوصول ويعمل على مدار الساعة — احتفظ برقم المرجع.",
        "hi": "📦 आपकी खोई वस्तु की रिपोर्ट दर्ज हो गई है (संदर्भ {ref})। {match} लॉस्ट एंड फ़ाउंड अराइवल हॉल के निकास के पास है और 24/7 खुला है — अपना संदर्भ नंबर संभालकर रखें।"},
    "lost_match": {
        "en": "A possible match has been found — the Lost & Found team will verify ownership with you (we can't confirm it in chat).",
        "ar": "تم العثور على غرض قد يكون مطابقاً — سيتحقق فريق المفقودات من الملكية معك (لا يمكننا التأكيد عبر المحادثة).",
        "hi": "एक संभावित मिलती-जुलती वस्तु मिली है — लॉस्ट एंड फ़ाउंड टीम आपके साथ स्वामित्व की पुष्टि करेगी (हम चैट में इसकी पुष्टि नहीं कर सकते)।"},
    "lost_nomatch": {
        "en": "No match yet — new found items are checked against your report automatically.",
        "ar": "لا يوجد تطابق حتى الآن — ستتم مقارنة المفقودات الجديدة ببلاغك تلقائياً.",
        "hi": "अभी कोई मेल नहीं — नई मिली वस्तुओं का मिलान आपकी रिपोर्ट से अपने-आप किया जाएगा।"},
    "blocked": {
        "en": "🚫 I can't process that request. I can help with flight status, gates, walking times, assistance and airport information.",
        "ar": "🚫 لا يمكنني تنفيذ هذا الطلب. يمكنني المساعدة في حالة الرحلات والبوابات وأوقات المشي وطلبات المساعدة ومعلومات المطار.",
        "hi": "🚫 मैं यह अनुरोध पूरा नहीं कर सकता। मैं उड़ान की स्थिति, गेट, चलने का समय, सहायता और एयरपोर्ट जानकारी में मदद कर सकता हूँ।"},
    "greeting": {
        "en": "👋 Hi! I'm the Sahra Airport assistant. Ask me about your gate, flight status, walking time to the gate, baggage belts, lost items or assistance.",
        "ar": "👋 مرحباً! أنا مساعد مطار صحراء. اسألني عن بوابتك وحالة رحلتك ووقت المشي إلى البوابة وأحزمة الأمتعة والمفقودات أو طلب المساعدة.",
        "hi": "👋 नमस्ते! मैं सहरा एयरपोर्ट असिस्टेंट हूँ। मुझसे अपने गेट, उड़ान की स्थिति, गेट तक चलने का समय, बैगेज बेल्ट, खोई वस्तुओं या सहायता के बारे में पूछें।"},
    "held_fallback": {
        "en": "I can't confirm that right now, so I won't guess. Please check the screens or ask any staff member.",
        "ar": "لا يمكنني تأكيد ذلك الآن، لذلك لن أخمّن. يرجى مراجعة الشاشات أو سؤال أي موظف.",
        "hi": "मैं अभी इसकी पुष्टि नहीं कर सकता, इसलिए अनुमान नहीं लगाऊँगा। कृपया स्क्रीन देखें या किसी स्टाफ सदस्य से पूछें।"},
}

FIELD_LABEL = {
    "gate": {"en": "gate", "ar": "رقم البوابة", "hi": "गेट"},
    "status": {"en": "flight status", "ar": "حالة الرحلة", "hi": "उड़ान की स्थिति"},
    "boarding_time": {"en": "boarding time", "ar": "وقت الصعود", "hi": "बोर्डिंग समय"},
    "est_time": {"en": "departure time", "ar": "وقت المغادرة", "hi": "प्रस्थान समय"},
    "belt": {"en": "baggage belt", "ar": "حزام الأمتعة", "hi": "बैगेज बेल्ट"},
}
JOIN = {"en": " and ", "ar": " و", "hi": " और "}
STATUS_LABEL = {
    "ON_TIME": {"en": "On time", "ar": "في الموعد", "hi": "समय पर"},
    "BOARDING": {"en": "Boarding", "ar": "الصعود جارٍ", "hi": "बोर्डिंग जारी"},
    "DELAYED": {"en": "Delayed", "ar": "متأخرة", "hi": "विलंबित"},
    "GATE_CLOSED": {"en": "Gate closed", "ar": "البوابة مغلقة", "hi": "गेट बंद"},
    "DEPARTED": {"en": "Departed", "ar": "غادرت", "hi": "रवाना"},
    "CANCELLED": {"en": "Cancelled", "ar": "ملغاة", "hi": "रद्द"},
    "LANDED": {"en": "Landed", "ar": "هبطت", "hi": "उतर गई"},
    "EXPECTED": {"en": "Expected", "ar": "متوقعة", "hi": "अपेक्षित"},
}


def t(key, lang="en", **kw):
    tpl = T[key].get(lang) or T[key]["en"]
    return tpl.format(**kw)


def fields_label(fields, lang):
    return JOIN.get(lang, " and ").join(FIELD_LABEL[f].get(lang, FIELD_LABEL[f]["en"]) for f in fields)


def fmt(field, value, lang="en"):
    if value is None:
        return "—"
    if field in ("boarding_time", "est_time"):
        return clock.hhmm(value)
    if field == "status":
        return STATUS_LABEL.get(value, {}).get(lang, value.replace("_", " ").title())
    return str(value)
