"use client";

/** Minimal EN/ES translation context. No routing, no external i18n library —
 * a single client-side dictionary lookup is enough for a two-language demo UI.
 * Persists the chosen locale to localStorage. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type Locale = "en" | "es";

const LOCALE_KEY = "terrasignal_locale";

type Dict = { [key: string]: string | Dict };

const en = {
  common: {
    band: { green: "Low", amber: "Watch", red: "High" },
    loading: "Loading…",
    unpaid: "unpaid",
  },
  nav: {
    portfolio: "Portfolio",
    riskQueue: "Risk Queue",
    pricing: "Pricing",
    governance: "Governance",
    signOut: "Sign out",
  },
  roles: {
    analyst: "Analyst",
    approver: "Approver",
    admin: "Admin",
  },
  login: {
    tagline: "CRE rent forecasting & tenant risk",
    username: "Username",
    password: "Password",
    signIn: "Sign in",
    signingIn: "Signing in…",
    signInFailed: "Sign-in failed",
    demoUsers: "Demo users (password: demo)",
    demoAnalyst: "Analyst — scores & overrides",
    demoApprover: "Approver — model approvals, audit",
    demoAdmin: "Admin — kill switch",
  },
  dashboard: {
    title: "Portfolio",
    subtitle: "As of {date} · {count} properties",
    noiAtRisk: "NOI at risk (annual)",
    noiAtRiskHint: "Watchlist tenants' in-place rent",
    watchlistTenants: "Watchlist tenants",
    watchlistHint: "Avg PD {pct}",
    renewalUpside: "Renewal upside (annual)",
    renewalUpsideHint: "If priced units renew at p50",
    activeLeases: "Active leases",
    activeLeasesHint: "{rsf}M RSF",
    riskDistribution: "Tenant risk distribution",
    expirationWall: "Lease expiration wall",
    loadingPortfolio: "Loading portfolio…",
    errorNoData: "No portfolio data yet — run the demo seed + batch scoring, then refresh.",
    errorGeneric: "Failed to load portfolio.",
  },
  risk: {
    title: "Risk Queue",
    subtitle: "Tenants ranked by calibrated probability of default within 6 months",
    errorQueue: "Could not load the queue — is the backend seeded and scored?",
    colTenant: "Tenant",
    colIndustry: "Industry",
    colCredit: "Credit",
    colPd: "PD (6m)",
    colTopDriver: "Top driver",
    colTrend: "Days-late trend",
    notRatedShort: "NR",
    empty: "No scored tenants yet. Run batch scoring to populate the queue.",
  },
  tenant: {
    back: "← Risk Queue",
    errorNotFound: "Tenant not found, or the backend isn’t seeded.",
    scoreNow: "Score now",
    scoring: "Scoring…",
    defaultRisk: "Default risk",
    scoreMeta: "Calibrated PD within 6 months · model v{version} · {source} · as of {date}",
    sourceBaseline: "baseline heuristic",
    sourceModel: "model",
    whyThisScore: "Why this score",
    noScoreYet: "No score yet. Use {scoreNow} to generate one.",
    tenantCard: "Tenant",
    industry: "Industry",
    creditRating: "Credit rating",
    notRated: "Not rated",
    activeLeases: "Active leases",
    leases: "Leases",
    colLease: "Lease",
    colProperty: "Property",
    colBaseRent: "Base rent",
    colRsf: "RSF",
    colExpires: "Expires",
    recentPayments: "Recent payments",
    colDue: "Due",
    colPaid: "Paid",
    colAmountDue: "Amount due",
    colDaysLate: "Days late",
  },
  pricing: {
    title: "Lease Pricing",
    subtitle: "Renewal rent forecast with comps, drivers, and a grounded rationale memo",
    errorQueue: "Could not load the renewal queue — seed + score first.",
    upcomingRenewals: "Upcoming renewals",
    unitMeta: "{unitId} · {submarket} · exp {date}",
    emptyRenewals: "No renewals queued.",
    selectUnit: "Select a unit to forecast its renewal rent.",
    errorNoLease: "This unit has no active lease to renew.",
    metricP50: "p50 renewal",
    metricInPlace: "in-place",
    metricUpside: "upside",
    metricComp: "submarket comp (6m)",
    footerMeta: "{assetClass} · {submarket} · {rsf} RSF · model v{version}",
    footerBaseline: " · baseline heuristic",
    driversTitle: "What drives the estimate",
    compsTitle: "Nearest comps",
    colSigned: "Signed",
    colRent: "Rent",
    colTerm: "Term",
    colTi: "TI",
    colFree: "Free",
    emptyComps: "Thin submarket — no recent comps.",
    decisionTitle: "Pricing decision",
    rationaleTitle: "Rationale memo",
    generateMemo: "Generate memo",
    regenerate: "Regenerate",
    generating: "Generating…",
    guardPassed: "numeric guard passed",
    guardFailed: "numeric guard failed",
    templateFallback: "template fallback",
    rationalePlaceholder:
      "Generate a grounded narrative — the model verbalizes the numbers above; a post-check rejects any figure not present in the forecast payload.",
  },
  governance: {
    title: "Model Governance",
    subtitle: "Active versions, approvals, drift, audit trail, and the kill switch",
    tabKillSwitch: "Kill switch",
    tabModels: "Models",
    tabDrift: "Drift",
    tabAudit: "Audit",
    killSwitchTitle: "Baseline-mode kill switch",
    killSwitchBody:
      "Engaging baseline mode pauses both models instantly (no redeploy). Scoring and forecasting fall back to clearly-labeled comp-median heuristics, and the flip is written to the audit trail.",
    currentState: "Current state:",
    baselinePaused: "Baseline (models paused)",
    liveServing: "Live (models serving)",
    applying: "Applying…",
    restoreModels: "Restore models",
    engageKillSwitch: "Engage kill switch",
    adminOnly: "Requires the admin role to flip.",
    errorFlip: "Failed to flip the switch",
    colModel: "Model",
    colVersion: "Ver",
    colStatus: "Status",
    colMetrics: "Key metrics",
    colApproved: "Approved",
    approve: "Approve",
    errorRegistry: "Could not load the registry.",
    errorApprove: "Approval failed",
    colFeature: "Feature",
    colPsi: "PSI",
    colComputed: "Computed",
    errorDrift: "Could not load drift metrics.",
    emptyDrift: "No drift metrics computed yet.",
    colWhen: "When",
    colActor: "Actor",
    colEvent: "Event",
    colEntity: "Entity",
    errorAuditForbidden: "Requires the approver role.",
    errorAudit: "Could not load the audit trail.",
  },
  banner: {
    baseline:
      "Baseline mode is engaged — models are paused. All scores and forecasts shown are comp-median heuristics, not model outputs.",
  },
  feedback: {
    reasonMarket: "Market knowledge",
    reasonRelationship: "Tenant relationship",
    reasonDataQuality: "Data quality concern",
    reasonStrategic: "Strategic decision",
    reasonDistrust: "Model distrust",
    reasonOther: "Other",
    recordedAccept: "Recorded acceptance — written to the audit trail.",
    recordedOverride: "Recorded override — written to the audit trail.",
    accept: "Accept",
    override: "Override…",
    reasonCodeLabel: "Reason code (required)",
    commentLabel: "Comment",
    commentPlaceholder: "What does the model miss here?",
    submitOverride: "Submit override",
    cancel: "Cancel",
    errorGeneric: "Failed to record feedback",
  },
  charts: {
    tenantsUnit: "tenants",
    countLabel: "Count",
    pdLabel: "PD {label}",
    annualRent: "Annual rent",
    leases: "Leases",
  },
  shap: {
    empty: "No driver attribution available.",
  },
  themeToggle: {
    light: "Light",
    dark: "Dark",
  },
} satisfies Dict;

const es = {
  common: {
    band: { green: "Bajo", amber: "Vigilar", red: "Alto" },
    loading: "Cargando…",
    unpaid: "sin pagar",
  },
  nav: {
    portfolio: "Portafolio",
    riskQueue: "Cola de riesgo",
    pricing: "Precios",
    governance: "Gobernanza",
    signOut: "Cerrar sesión",
  },
  roles: {
    analyst: "Analista",
    approver: "Aprobador",
    admin: "Administrador",
  },
  login: {
    tagline: "Pronóstico de renta CRE y riesgo de inquilinos",
    username: "Usuario",
    password: "Contraseña",
    signIn: "Iniciar sesión",
    signingIn: "Iniciando sesión…",
    signInFailed: "Error al iniciar sesión",
    demoUsers: "Usuarios de demostración (contraseña: demo)",
    demoAnalyst: "Analista — puntajes y anulaciones",
    demoApprover: "Aprobador — aprobación de modelos, auditoría",
    demoAdmin: "Administrador — interruptor de emergencia",
  },
  dashboard: {
    title: "Portafolio",
    subtitle: "Al {date} · {count} propiedades",
    noiAtRisk: "NOI en riesgo (anual)",
    noiAtRiskHint: "Renta vigente de inquilinos en vigilancia",
    watchlistTenants: "Inquilinos en vigilancia",
    watchlistHint: "PD promedio {pct}",
    renewalUpside: "Potencial de renovación (anual)",
    renewalUpsideHint: "Si las unidades cotizadas renuevan al p50",
    activeLeases: "Contratos activos",
    activeLeasesHint: "{rsf}M RSF",
    riskDistribution: "Distribución de riesgo de inquilinos",
    expirationWall: "Muro de vencimientos de contratos",
    loadingPortfolio: "Cargando portafolio…",
    errorNoData:
      "Aún no hay datos de portafolio — ejecuta la semilla de demostración y el scoring por lotes, luego actualiza.",
    errorGeneric: "No se pudo cargar el portafolio.",
  },
  risk: {
    title: "Cola de riesgo",
    subtitle: "Inquilinos ordenados por probabilidad de incumplimiento calibrada a 6 meses",
    errorQueue: "No se pudo cargar la cola — ¿el backend tiene datos y scoring?",
    colTenant: "Inquilino",
    colIndustry: "Industria",
    colCredit: "Crédito",
    colPd: "PD (6m)",
    colTopDriver: "Factor principal",
    colTrend: "Tendencia de días de atraso",
    notRatedShort: "SC",
    empty: "Aún no hay inquilinos evaluados. Ejecuta el scoring por lotes para poblar la cola.",
  },
  tenant: {
    back: "← Cola de riesgo",
    errorNotFound: "Inquilino no encontrado, o el backend no tiene datos cargados.",
    scoreNow: "Evaluar ahora",
    scoring: "Evaluando…",
    defaultRisk: "Riesgo de incumplimiento",
    scoreMeta: "PD calibrada a 6 meses · modelo v{version} · {source} · al {date}",
    sourceBaseline: "heurística de referencia",
    sourceModel: "modelo",
    whyThisScore: "Por qué este puntaje",
    noScoreYet: "Aún no hay puntaje. Usa {scoreNow} para generar uno.",
    tenantCard: "Inquilino",
    industry: "Industria",
    creditRating: "Calificación crediticia",
    notRated: "Sin calificación",
    activeLeases: "Contratos activos",
    leases: "Contratos",
    colLease: "Contrato",
    colProperty: "Propiedad",
    colBaseRent: "Renta base",
    colRsf: "RSF",
    colExpires: "Vence",
    recentPayments: "Pagos recientes",
    colDue: "Vencimiento",
    colPaid: "Pagado",
    colAmountDue: "Monto adeudado",
    colDaysLate: "Días de atraso",
  },
  pricing: {
    title: "Precios de arrendamiento",
    subtitle: "Pronóstico de renta de renovación con comparables, factores y un memo razonado",
    errorQueue: "No se pudo cargar la cola de renovaciones — carga datos y evalúa primero.",
    upcomingRenewals: "Próximas renovaciones",
    unitMeta: "{unitId} · {submarket} · vence {date}",
    emptyRenewals: "No hay renovaciones en cola.",
    selectUnit: "Selecciona una unidad para pronosticar su renta de renovación.",
    errorNoLease: "Esta unidad no tiene un contrato activo para renovar.",
    metricP50: "renovación p50",
    metricInPlace: "renta vigente",
    metricUpside: "potencial",
    metricComp: "comparable de submercado (6m)",
    footerMeta: "{assetClass} · {submarket} · {rsf} RSF · modelo v{version}",
    footerBaseline: " · heurística de referencia",
    driversTitle: "Qué impulsa la estimación",
    compsTitle: "Comparables más cercanos",
    colSigned: "Firmado",
    colRent: "Renta",
    colTerm: "Plazo",
    colTi: "TI",
    colFree: "Gratis",
    emptyComps: "Submercado con pocos datos — sin comparables recientes.",
    decisionTitle: "Decisión de precio",
    rationaleTitle: "Memo razonado",
    generateMemo: "Generar memo",
    regenerate: "Regenerar",
    generating: "Generando…",
    guardPassed: "verificación numérica aprobada",
    guardFailed: "verificación numérica fallida",
    templateFallback: "plantilla de respaldo",
    rationalePlaceholder:
      "Genera una narrativa razonada — el modelo describe en palabras las cifras de arriba; una verificación posterior rechaza cualquier valor que no esté en los datos del pronóstico.",
  },
  governance: {
    title: "Gobernanza de modelos",
    subtitle: "Versiones activas, aprobaciones, drift, auditoría e interruptor de emergencia",
    tabKillSwitch: "Interruptor",
    tabModels: "Modelos",
    tabDrift: "Drift",
    tabAudit: "Auditoría",
    killSwitchTitle: "Interruptor de modo de referencia",
    killSwitchBody:
      "Activar el modo de referencia pausa ambos modelos al instante (sin redepliegue). El scoring y los pronósticos usan heurísticas de mediana comparable claramente etiquetadas, y el cambio queda registrado en la auditoría.",
    currentState: "Estado actual:",
    baselinePaused: "Referencia (modelos pausados)",
    liveServing: "En vivo (modelos activos)",
    applying: "Aplicando…",
    restoreModels: "Restaurar modelos",
    engageKillSwitch: "Activar interruptor",
    adminOnly: "Se requiere el rol de administrador para cambiarlo.",
    errorFlip: "No se pudo cambiar el interruptor",
    colModel: "Modelo",
    colVersion: "Ver",
    colStatus: "Estado",
    colMetrics: "Métricas clave",
    colApproved: "Aprobado",
    approve: "Aprobar",
    errorRegistry: "No se pudo cargar el registro.",
    errorApprove: "Error al aprobar",
    colFeature: "Característica",
    colPsi: "PSI",
    colComputed: "Calculado",
    errorDrift: "No se pudieron cargar las métricas de drift.",
    emptyDrift: "Aún no se han calculado métricas de drift.",
    colWhen: "Cuándo",
    colActor: "Actor",
    colEvent: "Evento",
    colEntity: "Entidad",
    errorAuditForbidden: "Se requiere el rol de aprobador.",
    errorAudit: "No se pudo cargar la auditoría.",
  },
  banner: {
    baseline:
      "El modo de referencia está activo — los modelos están pausados. Todos los puntajes y pronósticos mostrados son heurísticas de mediana comparable, no salidas del modelo.",
  },
  feedback: {
    reasonMarket: "Conocimiento de mercado",
    reasonRelationship: "Relación con el inquilino",
    reasonDataQuality: "Problema de calidad de datos",
    reasonStrategic: "Decisión estratégica",
    reasonDistrust: "Desconfianza del modelo",
    reasonOther: "Otro",
    recordedAccept: "Aceptación registrada — escrita en la auditoría.",
    recordedOverride: "Anulación registrada — escrita en la auditoría.",
    accept: "Aceptar",
    override: "Anular…",
    reasonCodeLabel: "Código de motivo (obligatorio)",
    commentLabel: "Comentario",
    commentPlaceholder: "¿Qué se le escapa al modelo aquí?",
    submitOverride: "Enviar anulación",
    cancel: "Cancelar",
    errorGeneric: "No se pudo registrar la retroalimentación",
  },
  charts: {
    tenantsUnit: "inquilinos",
    countLabel: "Cantidad",
    pdLabel: "PD {label}",
    annualRent: "Renta anual",
    leases: "Contratos",
  },
  shap: {
    empty: "No hay atribución de factores disponible.",
  },
  themeToggle: {
    light: "Claro",
    dark: "Oscuro",
  },
} satisfies Dict;

const DICTS: Record<Locale, Dict> = { en, es };

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleState | null>(null);

function lookup(dict: Dict, key: string): string | undefined {
  let node: Dict | string = dict;
  for (const part of key.split(".")) {
    if (typeof node === "string") return undefined;
    const next: Dict | string | undefined = node[part];
    if (next === undefined) return undefined;
    node = next;
  }
  return typeof node === "string" ? node : undefined;
}

function interpolate(str: string, vars?: Record<string, string | number>): string {
  if (!vars) return str;
  return str.replace(/\{(\w+)\}/g, (match, key: string) =>
    vars[key] !== undefined ? String(vars[key]) : match,
  );
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    const stored = window.localStorage.getItem(LOCALE_KEY) as Locale | null;
    if (stored === "en" || stored === "es") setLocaleState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    window.localStorage.setItem(LOCALE_KEY, next);
    setLocaleState(next);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const raw = lookup(DICTS[locale], key) ?? lookup(DICTS.en, key) ?? key;
      return interpolate(raw, vars);
    },
    [locale],
  );

  const value = useMemo<LocaleState>(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleState {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}
