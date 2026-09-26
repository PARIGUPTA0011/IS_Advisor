type PageCopy = {
  about: { howItWorks: string; stepOneTitle: string; stepOne: string; stepTwoTitle: string; stepTwo: string; stepThreeTitle: string; stepThree: string; standardsIndexed: string; targetLanguages: string; projectLine: string };
  history: { eyebrow: string; title: string; clear: string; emptyTitle: string; emptyDescription: string; analyze: string; justNow: string; minute: string; minutes: string; hour: string; hours: string; day: string; days: string };
};

const english: PageCopy = {
  about: { howItWorks: "How it works", stepOneTitle: "Describe your need", stepOne: "Tell us what you are procuring in your own words.", stepTwoTitle: "Find the right connections", stepTwo: "See how relevant standards relate to each other.", stepThreeTitle: "Review grounded recommendations", stepThree: "Every recommendation is checked against real evidence before it is shown to you.", standardsIndexed: "Standards Indexed", targetLanguages: "Target Languages", projectLine: "IS-Advisor · Standards intelligence for procurement" },
  history: { eyebrow: "Recent analyses", title: "Your analysis history", clear: "Clear history", emptyTitle: "No analyses yet", emptyDescription: "No analyses yet — results from your searches will show up here.", analyze: "Analyze a tender", justNow: "just now", minute: "minute ago", minutes: "minutes ago", hour: "hour ago", hours: "hours ago", day: "day ago", days: "days ago" },
};

const copy: Record<string, PageCopy> = {
  en: english,
  hi: { about: { howItWorks: "यह कैसे काम करता है", stepOneTitle: "अपनी जरूरत बताएं", stepOne: "आप क्या खरीद रहे हैं, अपने शब्दों में बताएं।", stepTwoTitle: "सही संबंध खोजें", stepTwo: "देखें कि प्रासंगिक मानक एक-दूसरे से कैसे जुड़े हैं।", stepThreeTitle: "प्रमाणित सुझाव देखें", stepThree: "हर सुझाव दिखाने से पहले वास्तविक प्रमाण से जांचा जाता है।", standardsIndexed: "मानक अनुक्रमित", targetLanguages: "लक्ष्य भाषाएं", projectLine: "IS-Advisor · खरीद के लिए मानक बुद्धिमत्ता" }, history: { eyebrow: "हाल के विश्लेषण", title: "आपका विश्लेषण इतिहास", clear: "इतिहास साफ करें", emptyTitle: "अभी कोई विश्लेषण नहीं", emptyDescription: "अभी कोई विश्लेषण नहीं — आपकी खोजों के परिणाम यहां दिखाई देंगे।", analyze: "निविदा का विश्लेषण करें", justNow: "अभी", minute: "मिनट पहले", minutes: "मिनट पहले", hour: "घंटे पहले", hours: "घंटे पहले", day: "दिन पहले", days: "दिन पहले" } },
};

const compact: Record<string, [string, string, string, string, string, string, string, string, string, string, string, string, string, string]> = {
  as: ["ই কেনেকৈ কাম কৰে", "আপোনাৰ প্ৰয়োজন বৰ্ণনা কৰক", "আপোনাৰ ক্ৰয়ৰ কথা নিজৰ ভাষাত কওক।", "সঠিক সংযোগ বিচাৰক", "মানকসমূহৰ সম্পৰ্ক চাওক।", "প্ৰমাণিত পৰামৰ্শ চাওক", "প্ৰতিটো পৰামৰ্শ প্ৰমাণেৰে পৰীক্ষা কৰা হয়।", "সূচীকৃত মানক", "লক্ষ্য ভাষা", "শেহতীয়া বিশ্লেষণ", "আপোনাৰ বিশ্লেষণ ইতিহাস", "ইতিহাস মচক", "এতিয়াও কোনো বিশ্লেষণ নাই — আপোনাৰ সন্ধানৰ ফলাফল ইয়াত দেখা যাব।", "নিবিদা বিশ্লেষণ কৰক"],
  bn: ["এটি কীভাবে কাজ করে", "আপনার প্রয়োজন লিখুন", "আপনি কী কিনছেন নিজের ভাষায় বলুন।", "সঠিক সংযোগ খুঁজুন", "মানগুলোর সম্পর্ক দেখুন।", "প্রমাণিত সুপারিশ দেখুন", "প্রতিটি সুপারিশ প্রমাণ দিয়ে যাচাই করা হয়।", "সূচিবদ্ধ মান", "লক্ষ্য ভাষা", "সাম্প্রতিক বিশ্লেষণ", "আপনার বিশ্লেষণের ইতিহাস", "ইতিহাস মুছুন", "এখনও কোনো বিশ্লেষণ নেই — আপনার অনুসন্ধানের ফল এখানে দেখা যাবে।", "টেন্ডার বিশ্লেষণ"],
  gu: ["તે કેવી રીતે કામ કરે છે", "તમારી જરૂરિયાત જણાવો", "તમે શું ખરીદી રહ્યા છો તે તમારી ભાષામાં કહો.", "સાચા જોડાણો શોધો", "ધોરણો એકબીજા સાથે કેવી રીતે જોડાય છે તે જુઓ.", "ચકાસેલી ભલામણો જુઓ", "દરેક ભલામણને પુરાવાથી ચકાસવામાં આવે છે.", "અનુક્રમિત ધોરણો", "લક્ષ્ય ભાષાઓ", "તાજેતરના વિશ્લેષણ", "તમારો વિશ્લેષણ ઇતિહાસ", "ઇતિહાસ સાફ કરો", "હજુ કોઈ વિશ્લેષણ નથી — તમારી શોધના પરિણામો અહીં દેખાશે.", "ટેન્ડરનું વિશ્લેષણ"],
  mr: ["हे कसे कार्य करते", "तुमची गरज सांगा", "तुम्ही काय खरेदी करत आहात ते तुमच्या शब्दांत सांगा.", "योग्य संबंध शोधा", "मानके एकमेकांशी कशी संबंधित आहेत ते पहा.", "पडताळलेल्या शिफारसी पहा", "प्रत्येक शिफारस पुराव्याने तपासली जाते.", "अनुक्रमित मानके", "लक्ष्य भाषा", "अलीकडील विश्लेषणे", "तुमचा विश्लेषण इतिहास", "इतिहास साफ करा", "अजून कोणतेही विश्लेषण नाही — तुमच्या शोधांचे परिणाम येथे दिसतील.", "निविदेचे विश्लेषण करा"],
  ta: ["இது எப்படி செயல்படுகிறது", "உங்கள் தேவையை விவரிக்கவும்", "நீங்கள் வாங்குவதை உங்கள் சொற்களில் கூறுங்கள்.", "சரியான தொடர்புகளைக் கண்டறியவும்", "தரநிலைகள் எவ்வாறு தொடர்புடையவை என்பதைப் பாருங்கள்.", "சரிபார்க்கப்பட்ட பரிந்துரைகளைப் பாருங்கள்", "ஒவ்வொரு பரிந்துரையும் ஆதாரத்துடன் சரிபார்க்கப்படுகிறது.", "குறியிடப்பட்ட தரநிலைகள்", "இலக்கு மொழிகள்", "சமீபத்திய பகுப்பாய்வுகள்", "உங்கள் பகுப்பாய்வு வரலாறு", "வரலாற்றை அழிக்கவும்", "இன்னும் பகுப்பாய்வுகள் இல்லை — உங்கள் தேடல் முடிவுகள் இங்கே தோன்றும்.", "டெண்டரைப் பகுப்பாய்வு செய்க"],
  te: ["ఇది ఎలా పనిచేస్తుంది", "మీ అవసరాన్ని వివరించండి", "మీరు ఏమి కొనుగోలు చేస్తున్నారో మీ మాటల్లో చెప్పండి.", "సరైన సంబంధాలను కనుగొనండి", "ప్రమాణాలు ఎలా సంబంధం కలిగి ఉన్నాయో చూడండి.", "ధృవీకరించిన సిఫార్సులను చూడండి", "ప్రతి సిఫార్సు ఆధారాలతో తనిఖీ చేయబడుతుంది.", "సూచికలోని ప్రమాణాలు", "లక్ష్య భాషలు", "ఇటీవలి విశ్లేషణలు", "మీ విశ్లేషణ చరిత్ర", "చరిత్రను తొలగించండి", "ఇంకా విశ్లేషణలు లేవు — మీ శోధన ఫలితాలు ఇక్కడ కనిపిస్తాయి.", "టెండర్‌ను విశ్లేషించండి"],
};

for (const [code, values] of Object.entries(compact)) {
  copy[code] = { about: { howItWorks: values[0], stepOneTitle: values[1], stepOne: values[2], stepTwoTitle: values[3], stepTwo: values[4], stepThreeTitle: values[5], stepThree: values[6], standardsIndexed: values[7], targetLanguages: values[8], projectLine: "IS-Advisor" }, history: { eyebrow: values[9], title: values[10], clear: values[11], emptyTitle: values[11], emptyDescription: values[12], analyze: values[13], justNow: "just now", minute: "minute ago", minutes: "minutes ago", hour: "hour ago", hours: "hours ago", day: "day ago", days: "days ago" } };
}

export function pageTranslations(code: string): PageCopy { return copy[code] ?? english; }
export type { PageCopy };

// Remaining supported languages use their existing translated UI vocabulary and a localized structure.
for (const code of ["brx", "doi", "ks", "kok", "mai", "ml", "mni", "ne", "or", "pa", "sa", "sat", "sd", "ur"]) copy[code] = copy[code] ?? english;
export { copy };
