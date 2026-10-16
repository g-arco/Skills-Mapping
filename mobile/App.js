import React, { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import * as DocumentPicker from "expo-document-picker";

// react-native-webview is only needed on native (iOS/Android).
// On web we render a plain <iframe>, so this import is guarded
// so the app doesn't crash if the package isn't installed.
let WebView = null;
if (Platform.OS !== "web") {
  try {
    WebView = require("react-native-webview").WebView;
  } catch (e) {
    WebView = null;
  }
}

const isWeb = Platform.OS === "web" || typeof document !== "undefined";
const apiHost = isWeb ? "http://localhost:8000" : "http://127.0.0.1:8000";
const API_URL = `${apiHost}/ranking`;
const ENGAGEMENT_API_URL = `${apiHost}/engagement-ranking`;
const CHARTS_URL = `${apiHost}/charts`;

// ---------------------------------------------------------------------------
// Design tokens — blue/white theme, matching the backend /charts dashboard
// ---------------------------------------------------------------------------
const INK = "#0F2540";
const INK_SOFT = "#2C4A6E";
const PAPER = "#FFFFFF";
const PANEL = "#FFFFFF";
const CELL = "#EAF2FF";
const LINE = "#D7E3F7";
const LINE_SOFT = "#EAF2FF";
const BLUE_DARK = "#1D4ED8";
const BLUE = "#2563EB";
const BLUE_MID = "#3B82F6";
const BLUE_LIGHT = "#60A5FA"; // for accents on the dark top bar (contrast)
const BLUE_PALE = "#93C5FD"; // for the busiest/lightest status state
const MUTED = "#5B6B82";
const HEADING = "Montserrat, Avenir Next, Segoe UI, sans-serif";
const BODY = "DM Sans, Avenir Next, Segoe UI, sans-serif";
const MONO = HEADING;

const scoreTier = (score) => {
  if (score >= 0.75) return "high";
  if (score >= 0.5) return "mid";
  return "low";
};
// Score strength as blue intensity (darker/more saturated = stronger match)
// rather than a green/amber/red system, to match the blue/white theme used
// on the backend charts dashboard.
const TIER_COLOR = { high: BLUE_DARK, mid: BLUE_MID, low: MUTED };

export default function App() {
  const { width } = useWindowDimensions();
  const isNarrow = width < 900;
  const isStacked = width < 720;

  const [resumeText, setResumeText] = useState("");
  const [userLevel, setUserLevel] = useState("beginner");
  const [targetPathways, setTargetPathways] = useState("");
  const [eduEmail, setEduEmail] = useState("");
  const [language, setLanguage] = useState("english");
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Ready");
  const [progressSteps, setProgressSteps] = useState([]);
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [chartsKey, setChartsKey] = useState(0); // bump to force chart refresh
  const [lastUpdated, setLastUpdated] = useState(null);

  const [resumeOpen, setResumeOpen] = useState(true);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [progressOpen, setProgressOpen] = useState(true);

  const addProgressStep = (step) => {
    setProgressSteps((prev) => [...prev, step]);
    setStatusMessage(step);
  };

  const resetProgress = () => {
    setProgressSteps([]);
    setStatusMessage("Ready");
  };

  const handleBackendResponse = (json) => {
    if (json.progress) {
      setProgressSteps((prev) => [
        ...prev,
        ...json.progress.map((entry) => `${entry.name.replace(/_/g, " ")}`),
      ]);
    }
    addProgressStep("Backend returned results.");
    setResults(json);
    // Refresh the charts panel now that new results exist
    setChartsKey((k) => k + 1);
    setLastUpdated(new Date());
  };

  const pickFile = async () => {
    setError("");
    resetProgress();
    addProgressStep("Opening file picker...");

    const result = await DocumentPicker.getDocumentAsync({
      type: ["application/pdf", "text/plain"],
      copyToCacheDirectory: false,
    });
    if (result.type !== "success") {
      addProgressStep("File picker closed without selection.");
      return;
    }

    addProgressStep(`Selected file: ${result.name}`);
    const uri = result.uri;
    const filename = result.name;

    setLoading(true);
    addProgressStep("Preparing file upload...");
    const formData = new FormData();

    if (isWeb) {
      const response = await fetch(uri);
      const blob = await response.blob();
      const file = new File([blob], filename, {
        type: filename.endsWith(".pdf") ? "application/pdf" : "text/plain",
      });
      formData.append("resume_file", file);
    } else {
      formData.append("resume_file", {
        uri,
        name: filename,
        type: filename.endsWith(".pdf") ? "application/pdf" : "text/plain",
      });
    }

    if (eduEmail.trim()) {
      formData.append("edu_email", eduEmail.trim());
    }
    formData.append("user_level", userLevel);
    formData.append("target_pathways", targetPathways);
    formData.append("top_n", "10");
    formData.append("language", language);
    formData.append("language", language);

    try {
      addProgressStep("Sending file to backend...");
      const apiResponse = await fetch(API_URL, {
        method: "POST",
        body: formData,
        headers: { Accept: "application/json" },
      });

      addProgressStep("Waiting for backend response...");
      const json = await apiResponse.json();

      if (!apiResponse.ok) {
        throw new Error(json.detail || JSON.stringify(json));
      }

      handleBackendResponse(json);
    } catch (err) {
      setError(err.message);
      setResults(null);
      addProgressStep("Upload failed.");
    } finally {
      setLoading(false);
    }
  };

  const submitText = async () => {
    setError("");
    resetProgress();

    if (!resumeText.trim()) {
      setError("Paste resume text or upload a PDF/text file first.");
      setStatusMessage("Waiting for resume input...");
      return;
    }

    setLoading(true);
    addProgressStep("Preparing resume text...");
    const formData = new FormData();
    formData.append("resume_text", resumeText);
    if (eduEmail.trim()) {
      formData.append("edu_email", eduEmail.trim());
    }
    formData.append("user_level", userLevel);
    formData.append("target_pathways", targetPathways);
    formData.append("top_n", "10");
    formData.append("language", language);
    formData.append("language", language);

    try {
      addProgressStep("Sending text to backend...");
      const apiResponse = await fetch(API_URL, {
        method: "POST",
        body: formData,
        headers: { Accept: "application/json" },
      });

      addProgressStep("Waiting for backend response...");
      const json = await apiResponse.json();
      if (!apiResponse.ok) {
        throw new Error(json.detail || JSON.stringify(json));
      }

      handleBackendResponse(json);
    } catch (err) {
      setError(err.message);
      setResults(null);
      addProgressStep("Request failed.");
    } finally {
      setLoading(false);
    }
  };

  const submitEngagement = async () => {
    setError("");
    resetProgress();
    if (!eduEmail.trim()) {
      setError("Enter an education email to use engagement history.");
      setStatusMessage("Waiting for education email...");
      return;
    }

    setLoading(true);
    addProgressStep("Preparing engagement profile...");
    const formData = new FormData();
    formData.append("edu_email", eduEmail.trim());
    formData.append("top_n", "10");
    formData.append("language", language);

    try {
      addProgressStep("Sending engagement history request...");
      const apiResponse = await fetch(ENGAGEMENT_API_URL, {
        method: "POST",
        body: formData,
        headers: { Accept: "application/json" },
      });
      const json = await apiResponse.json();
      if (!apiResponse.ok) {
        throw new Error(json.detail || JSON.stringify(json));
      }
      handleBackendResponse(json);
    } catch (err) {
      setError(err.message);
      setResults(null);
      addProgressStep("Engagement lookup failed.");
    } finally {
      setLoading(false);
    }
  };

  const refreshCharts = () => {
    setChartsKey((k) => k + 1);
    setLastUpdated(new Date());
  };

  // ---------------------------------------------------------------------
  // Derived data for the stat row + the three client-rendered mini-charts.
  // The 4th chart cell stays the live backend iframe/WebView.
  // ---------------------------------------------------------------------
  const recs = results?.recommendations || [];

  const stats = useMemo(() => {
    if (!recs.length) return null;
    const avgScore = recs.reduce((s, r) => s + r.recommendation_score, 0) / recs.length;
    const pathwayCounts = {};
    recs.forEach((r) => {
      pathwayCounts[r.primary_pathway] = (pathwayCounts[r.primary_pathway] || 0) + 1;
    });
    const topEntry = Object.entries(pathwayCounts).sort((a, b) => b[1] - a[1])[0];
    return {
      total: recs.length,
      avgScore,
      topPathway: topEntry ? topEntry[0] : "—",
      topPathwayCount: topEntry ? topEntry[1] : 0,
      pathwayCounts,
    };
  }, [recs]);

  return (
    <View style={styles.page}>
      {/* ---------------- TOP BAR ---------------- */}
      <View style={styles.topbar}>
        <View style={styles.brand}>
          <Text style={styles.kicker}>COURSE RECOMMENDATIONS</Text>
          <Text style={styles.title}>Skills Mapping</Text>
          <Text style={styles.subtitle}>
            Upload a resume to match your skills against the course catalog and see how well
            each course fits.
          </Text>
        </View>
        <View style={styles.statusPill}>
          <View style={[styles.dot, loading && styles.dotBusy]} />
          <Text style={styles.statusPillText}>
            {loading ? "Working…" : results ? `Done · ${recs.length} matches found` : "Ready"}
          </Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.shell}>
        {/* ---------------- STAT ROW ---------------- */}
        <View style={[styles.statRow, isStacked && styles.statRowStacked]}>
          <StatCard label="Unique courses considered" value={results ? String(results.courses_considered || 0) : "—"} sub="active courses in selected language" />
          <StatCard
            label="Avg. match score"
            value={stats ? stats.avgScore.toFixed(2) : "—"}
            sub="out of 1.00"
            accent
          />
          <StatCard
            label="Top pathway"
            value={stats ? stats.topPathway : "—"}
            sub={stats ? `${stats.topPathwayCount} of ${stats.total} courses` : "no results yet"}
            small
          />
          <StatCard label="Level submitted" value={userLevel || "—"} sub="from inputs panel" small />
        </View>

        {/* ---------------- COLUMNS ---------------- */}
        <View style={[styles.columns, isNarrow && styles.columnsNarrow]}>
          {/* INPUTS ------------------------------------------------------ */}
          <View style={[styles.panel, styles.colInputs, isNarrow && styles.colFull]}>
            <View style={styles.panelHead}>
              <Text style={styles.panelTitle}>INPUTS</Text>
            </View>
            <View style={styles.panelBody}>
              <CollapsibleGroup title="Resume" open={resumeOpen} onToggle={() => setResumeOpen((o) => !o)}>
                <Text style={styles.fieldLabel}>Resume text</Text>
                <TextInput
                  style={styles.textArea}
                  multiline
                  value={resumeText}
                  onChangeText={setResumeText}
                  placeholder="Paste resume text here"
                />
                <View style={styles.btnRow}>
                  <Pressable style={[styles.btn, styles.btnSecondary]} onPress={pickFile}>
                    <Text style={styles.btnSecondaryText}>Upload PDF/Text</Text>
                  </Pressable>
                  <Pressable style={[styles.btn, styles.btnPrimary]} onPress={submitText}>
                    <Text style={styles.btnPrimaryText}>Submit Text</Text>
                  </Pressable>
                </View>
                <Pressable style={[styles.btn, styles.btnEngagement]} onPress={submitEngagement}>
                  <Text style={styles.btnEngagementText}>Use engagement history (optional)</Text>
                </Pressable>
              </CollapsibleGroup>

              <CollapsibleGroup title="Preferences" open={prefsOpen} onToggle={() => setPrefsOpen((o) => !o)}>
                <Text style={styles.fieldLabel}>User level</Text>
                <TextInput style={styles.input} value={userLevel} onChangeText={setUserLevel} />

                <Text style={styles.fieldLabel}>Target pathways</Text>
                <TextInput
                  style={styles.input}
                  value={targetPathways}
                  onChangeText={setTargetPathways}
                  placeholder="e.g. Analytics, Data Engineering"
                />

                <Text style={styles.fieldLabel}>Education email (optional)</Text>
                <TextInput
                  style={styles.input}
                  value={eduEmail}
                  onChangeText={setEduEmail}
                  placeholder="name@edu.com"
                  autoCapitalize="none"
                  keyboardType="email-address"
                />

                <Text style={styles.fieldLabel}>Language</Text>
                <TextInput
                  style={styles.input}
                  value={language}
                  onChangeText={setLanguage}
                  placeholder="e.g. English, Spanish, French"
                  autoCapitalize="none"
                />
              </CollapsibleGroup>

              {error ? (
                <View style={styles.errorBanner}>
                  <Text style={styles.errorBannerText}>{error}</Text>
                </View>
              ) : null}

              {loading && <ActivityIndicator size="large" color={BLUE} style={styles.loader} />}

              <View style={[styles.progressStrip, progressOpen && styles.progressStripOpen]}>
                <Pressable style={styles.progressStripHead} onPress={() => setProgressOpen((o) => !o)}>
                  <Text style={styles.progressStripHeadText}>PROGRESS LOG</Text>
                  <Text style={styles.chev}>{progressOpen ? "▾" : "▸"}</Text>
                </Pressable>
                {progressOpen && (
                  <View style={styles.progressList}>
                    {progressSteps.length === 0 ? (
                      <Text style={styles.placeholder}>{statusMessage}</Text>
                    ) : (
                      progressSteps.map((step, index) => (
                        <View key={index} style={styles.progressItem}>
                          <Text style={styles.progressIdx}>{String(index + 1).padStart(2, "0")}</Text>
                          <Text style={styles.progressItemText}>{step}</Text>
                        </View>
                      ))
                    )}
                  </View>
                )}
              </View>
            </View>
          </View>

          {/* CHARTS (spans the middle two columns) ------------------------ */}
          <View style={[styles.panel, styles.colCharts, isNarrow && styles.colFull]}>
            <View style={styles.panelHead}>
              <Text style={styles.panelTitle}>CHARTS</Text>
              <View style={styles.chartsToolbar}>
                <Text style={styles.updated}>
                  {lastUpdated ? `updated ${lastUpdated.toLocaleTimeString()}` : "no data yet"}
                </Text>
                <Pressable style={styles.iconBtn} onPress={refreshCharts}>
                  <Text style={styles.iconBtnText}>⟳</Text>
                </Pressable>
              </View>
            </View>
            <View style={styles.panelBody}>
              {results ? (
              <>
                {results?.mode === "engagement" && results.engagement_profile ? (
                  <View style={styles.profileBanner}>
                    <Text style={styles.profileBannerTitle}>ENGAGEMENT PROFILE</Text>
                    <Text style={styles.profileBannerText}>
                      {results.engagement_profile.completed_courses} completed courses · next steps based on learned skills
                    </Text>
                    <Text style={styles.profileSectionTitle}>COMPLETED COURSES</Text>
                    {(results.engagement_profile.completed_course_details || []).map((course) => (
                      <View key={course.course_code} style={styles.profileRow}>
                        <Text style={styles.profileCode}>{course.course_code}</Text>
                        <Text style={styles.profileCourse}>{course.title}</Text>
                        <Text style={styles.profilePathway}>{course.primary_pathway}</Text>
                      </View>
                    ))}
                    {(results.engagement_profile.prerequisite_checks || []).length > 0 ? (
                      <>
                        <Text style={styles.profileSectionTitle}>PREREQUISITE CHECKS</Text>
                        {results.engagement_profile.prerequisite_checks.map((course) => (
                          <View key={course.course_code} style={styles.profileRow}>
                            <Text style={styles.profileCourse}>{course.title}</Text>
                            <Text style={styles.profileBannerText}>
                              {course.prerequisite_courses.map((prerequisite) =>
                                `${prerequisite.completed ? "Completed" : "Outstanding"}: ${prerequisite.title}`
                              ).join("; ")}
                            </Text>
                          </View>
                        ))}
                      </>
                    ) : null}
                    <Text style={styles.profileSectionTitle}>LEARNED SKILLS</Text>
                    <Text style={styles.profileBannerText}>
                      {(results.engagement_profile.learned_skills || []).join(", ") || "No skills were mapped from completed courses."}
                    </Text>
                  </View>
                ) : null}
                {/*
                The backend's /charts endpoint already renders the real
                analysis (pathway pie, skill-match histogram, relevance
                scatter, top-courses bar, plus history charts when
                available) from /feature_matrix, and the backend patches
                that same CSV so the bar chart always agrees with the
                Recommendations list. Re-deriving charts client-side from
                `recommendations` would risk showing numbers that disagree
                with this dashboard, so we embed it directly instead of
                reinventing it.
              */}
              <View style={styles.liveFrame}>
                {isWeb ? (
                  <iframe
                    key={chartsKey}
                    title="charts"
                    src={CHARTS_URL}
                    style={{ width: "100%", height: "100%", border: "none" }}
                  />
                ) : WebView ? (
                  <WebView key={chartsKey} source={{ uri: CHARTS_URL }} style={{ flex: 1 }} />
                ) : (
                  <Text style={styles.placeholder}>
                    Install react-native-webview to display charts on native platforms.
                  </Text>
                )}
              </View>
              </> 
              ) : (
                <Text style={styles.placeholder}>Run a recommendation to see charts and engagement insights.</Text>
              )}
            </View>
          </View>

          {/* RECOMMENDATIONS ---------------------------------------------- */}
          <View style={[styles.panel, styles.colRecs, isNarrow && styles.colFull]}>
            <View style={styles.panelHead}>
              <Text style={styles.panelTitle}>RECOMMENDATIONS</Text>
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{recs.length} results</Text>
              </View>
            </View>
            <View style={styles.panelBody}>
              {recs.length ? (
                recs.map((item, index) => {
                  const tier = scoreTier(item.recommendation_score);
                  return (
                    <View key={index} style={styles.recCard}>
                      <View style={styles.recMain}>
                        <View style={styles.recTop}>
                          <Text style={styles.recCode}>{item.course_code}</Text>
                          <Text style={styles.recTitle}>{item.title}</Text>
                        </View>
                        <View style={styles.recMeta}>
                          <Text style={styles.recMetaText}>{item.primary_pathway}</Text>
                          <Text style={styles.recMetaText}>·</Text>
                          <Text style={styles.recMetaText}>{item.language}</Text>
                        </View>
                      </View>
                      <View style={styles.scoreBlock}>
                        <Text style={[styles.scoreNum, { color: TIER_COLOR[tier] }]}>
                          {item.recommendation_score.toFixed(3)}
                        </Text>
                        <View style={styles.meter}>
                          <View
                            style={[
                              styles.meterFill,
                              {
                                width: `${Math.min(item.recommendation_score * 100, 100)}%`,
                                backgroundColor: TIER_COLOR[tier],
                              },
                            ]}
                          />
                        </View>
                      </View>
                    </View>
                  );
                })
              ) : (
                <Text style={styles.placeholder}>
                  Submit a resume or use engagement history to see recommended courses here.
                </Text>
              )}
            </View>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Small presentational subcomponents
// ---------------------------------------------------------------------------
function StatCard({ label, value, sub, accent, small }) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text
        style={[
          styles.statValue,
          accent && { color: BLUE },
          small && { fontSize: 18 },
        ]}
        numberOfLines={1}
      >
        {value}
      </Text>
      <Text style={styles.statSub}>{sub}</Text>
    </View>
  );
}

function CollapsibleGroup({ title, open, onToggle, children }) {
  return (
    <View style={styles.group}>
      <Pressable style={styles.groupHead} onPress={onToggle}>
        <Text style={styles.groupHeadText}>{title}</Text>
        <Text style={styles.chev}>{open ? "▾" : "▸"}</Text>
      </Pressable>
      {open && <View style={styles.groupBody}>{children}</View>}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  page: {
    flex: 1,
    backgroundColor: PAPER,
  },

  // Top bar
  topbar: {
    backgroundColor: INK,
    paddingTop: 24,
    paddingBottom: 20,
    paddingHorizontal: 24,
    borderBottomWidth: 3,
    borderBottomColor: BLUE,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 12,
  },
  brand: { flexShrink: 1, gap: 4 },
  kicker: {
    fontFamily: MONO,
    fontSize: 11,
    letterSpacing: 2,
    color: BLUE_LIGHT,
    textTransform: "uppercase",
  },
  title: {
    fontFamily: HEADING,
    fontSize: 26,
    fontWeight: "700",
    color: "#ffffff",
    letterSpacing: 0.2,
  },
  subtitle: {
    fontFamily: BODY,
    fontSize: 13,
    color: "#B9BDD1",
    maxWidth: 520,
    lineHeight: 19,
    marginTop: 2,
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "#1C263E",
    borderWidth: 1,
    borderColor: "#334064",
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 100,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: BLUE_LIGHT,
  },
  dotBusy: { backgroundColor: BLUE_PALE },
  statusPillText: {
    fontFamily: MONO,
    fontSize: 12,
    color: "#DCE0F0",
  },

  shell: {
    maxWidth: 1360,
    width: "100%",
    alignSelf: "center",
    padding: 16,
  },

  // Stat row
  statRow: {
    flexDirection: "row",
    gap: 12,
    marginBottom: 16,
  },
  statRowStacked: {
    flexDirection: "row",
    flexWrap: "wrap",
  },
  statCard: {
    flex: 1,
    minWidth: 140,
    backgroundColor: PANEL,
    borderWidth: 1,
    borderColor: LINE_SOFT,
    borderRadius: 12,
    padding: 14,
    shadowColor: INK,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
  statLabel: {
    fontFamily: MONO,
    fontSize: 10,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: MUTED,
    marginBottom: 6,
  },
  statValue: {
    fontFamily: BODY,
    fontSize: 22,
    fontWeight: "700",
    color: INK,
  },
  statSub: {
    fontFamily: BODY,
    fontSize: 11,
    color: MUTED,
    marginTop: 4,
  },

  // Columns
  columns: {
    flexDirection: "row",
    gap: 14,
    alignItems: "flex-start",
  },
  columnsNarrow: {
    flexDirection: "column",
  },
  colInputs: { flex: 0.9 },
  colCharts: { flex: 2 },
  colRecs: { flex: 0.9 },
  colFull: { flex: undefined, width: "100%" },

  panel: {
    backgroundColor: PANEL,
    borderRadius: 14,
    overflow: "hidden",
  },
  panelHead: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    height: 52,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: LINE_SOFT,
  },
  panelTitle: {
    fontFamily: MONO,
    fontSize: 11,
    letterSpacing: 1.4,
    color: INK_SOFT,
  },
  panelBody: { padding: 14 },
  badge: {
    backgroundColor: LINE_SOFT,
    borderRadius: 5,
    paddingVertical: 3,
    paddingHorizontal: 8,
  },
  badgeText: { fontFamily: MONO, fontSize: 11, color: INK_SOFT },

  // Input groups
  group: {
    borderWidth: 1,
    borderColor: LINE_SOFT,
    borderRadius: 10,
    marginBottom: 12,
    overflow: "hidden",
  },
  groupHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 11,
    paddingHorizontal: 14,
    backgroundColor: CELL,
  },
  groupHeadText: { fontFamily: BODY, fontSize: 13, fontWeight: "600", color: INK },
  groupBody: { padding: 14 },
  chev: { fontFamily: MONO, fontSize: 12, color: MUTED },

  fieldLabel: {
    fontFamily: BODY,
    fontSize: 12,
    fontWeight: "600",
    color: INK_SOFT,
    marginTop: 10,
    marginBottom: 5,
  },
  input: {
    fontFamily: BODY,
    borderWidth: 1,
    borderColor: LINE,
    borderRadius: 8,
    padding: 10,
    fontSize: 14,
    backgroundColor: "#fff",
    color: INK,
  },
  textArea: {
    fontFamily: BODY,
    borderWidth: 1,
    borderColor: LINE,
    borderRadius: 8,
    padding: 10,
    fontSize: 14,
    minHeight: 110,
    textAlignVertical: "top",
    backgroundColor: "#fff",
    color: INK,
  },
  btnRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  btn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: "center",
  },
  btnPrimary: { backgroundColor: INK },
  btnPrimaryText: { fontFamily: BODY, color: "#fff", fontSize: 13, fontWeight: "700" },
  btnSecondary: { backgroundColor: "#fff", borderWidth: 1, borderColor: LINE },
  btnSecondaryText: { fontFamily: BODY, color: INK, fontSize: 13, fontWeight: "700" },
  btnEngagement: { flex: 0, marginTop: 8, backgroundColor: "#EAF7F3", borderWidth: 1, borderColor: "#8CCDBB" },
  btnEngagementText: { fontFamily: BODY, color: "#176B59", fontSize: 13, fontWeight: "700" },

  profileBanner: {
    backgroundColor: "#F0F8F5",
    padding: 10,
    marginBottom: 12,
  },
  profileBannerTitle: { fontFamily: MONO, fontSize: 10, letterSpacing: 1, color: "#176B59", marginBottom: 4 },
  profileBannerText: { fontFamily: BODY, fontSize: 12, color: INK_SOFT },
  profileSectionTitle: { fontFamily: MONO, fontSize: 10, letterSpacing: 1, color: "#176B59", marginTop: 10, marginBottom: 5 },
  profileRow: { flexDirection: "row", gap: 8, paddingVertical: 4, borderTopWidth: 1, borderTopColor: "#D4E9E1" },
  profileCode: { fontFamily: MONO, fontSize: 10, color: "#176B59", width: 62 },
  profileCourse: { flex: 1, fontFamily: BODY, fontSize: 12, color: INK },
  profilePathway: { fontFamily: BODY, fontSize: 11, color: MUTED },

  errorBanner: {
    backgroundColor: "#FBEAE6",
    borderWidth: 1,
    borderColor: "#E3A99A",
    borderRadius: 8,
    padding: 10,
    marginTop: 4,
    marginBottom: 4,
  },
  errorBannerText: { fontFamily: BODY, color: "#A23B26", fontSize: 13 },
  loader: { marginTop: 12 },

  // Progress strip
  progressStrip: {
    marginTop: 14,
    borderWidth: 1,
    borderColor: LINE_SOFT,
    borderRadius: 10,
    overflow: "hidden",
  },
  progressStripOpen: {},
  progressStripHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 9,
    paddingHorizontal: 13,
  },
  progressStripHeadText: { fontFamily: MONO, fontSize: 11, color: MUTED },
  progressList: { paddingHorizontal: 13, paddingBottom: 12, gap: 4 },
  progressItem: {
    flexDirection: "row",
    gap: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: LINE_SOFT,
  },
  progressIdx: { fontFamily: MONO, fontSize: 12, color: BLUE, minWidth: 16 },
  progressItemText: { fontSize: 12, color: INK_SOFT, flexShrink: 1 },

  placeholder: { fontFamily: BODY, fontSize: 13, color: MUTED, paddingVertical: 4 },

  // Recommendation cards
  recCard: {
    flexDirection: "row",
    gap: 12,
    alignItems: "flex-start",
    borderRadius: 10,
    padding: 13,
    marginBottom: 10,
  },
  recMain: { flex: 1, minWidth: 0 },
  recTop: { flexDirection: "row", flexWrap: "wrap", alignItems: "baseline", gap: 8 },
  recCode: { fontFamily: MONO, fontSize: 12, fontWeight: "700", color: BLUE },
  recTitle: { fontFamily: BODY, fontSize: 14, fontWeight: "700", color: INK },
  recMeta: { flexDirection: "row", gap: 8, marginTop: 6 },
  recMetaText: { fontFamily: BODY, fontSize: 11.5, color: MUTED },
  scoreBlock: { width: 84, alignItems: "flex-end" },
  scoreNum: { fontFamily: MONO, fontSize: 16, fontWeight: "700" },
  meter: {
    width: "100%",
    height: 5,
    backgroundColor: LINE_SOFT,
    borderRadius: 3,
    marginTop: 6,
    overflow: "hidden",
  },
  meterFill: { height: "100%", borderRadius: 3 },

  // Charts panel
  chartsToolbar: { flexDirection: "row", alignItems: "center", gap: 10 },
  updated: { fontFamily: MONO, fontSize: 10.5, color: MUTED },
  iconBtn: {
    width: 26,
    height: 26,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: LINE,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
  },
  iconBtnText: { fontSize: 13, color: INK_SOFT },

  // The live backend dashboard (pie, histogram, scatter, bar, optional
  // history charts) stacks several full-size Plotly charts vertically, so
  // this frame is tall rather than a small grid cell. The outer ScrollView
  // on the page handles scrolling past it.
  liveFrame: {
    height: 1700,
    borderRadius: 8,
    overflow: "hidden",
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: LINE_SOFT,
    shadowColor: INK,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
});