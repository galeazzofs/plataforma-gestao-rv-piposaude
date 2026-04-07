# Plataforma de Comissões — Frontend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete ClojureScript/Reagent frontend SPA for the Pipo Saúde commission platform — design system, routing, state management, all views per persona, notifications.

**Architecture:** SPA em ClojureScript com Reagent (React wrapper), Re-frame (state), Reitit (routing), Emotion.js (styling). Comunica com backend Flask via REST API. Design system custom baseado nas cores/espaçamento da Pipo com princípios do Obentô.

**Tech Stack:** ClojureScript 1.11, Shadow-cljs, Reagent, Re-frame, Reitit, Emotion.js, cljs-ajax, Day.js, Recharts (gráficos), Docker + Nginx

**Spec:** `docs/superpowers/specs/2026-03-27-plataforma-comissoes-design.md`

**Depends on:** Backend plan must be complete (API endpoints available).

---

## File Structure

```
frontend/
├── src/
│   └── app/
│       ├── core.cljs                      # Entry point, mount app
│       ├── config.cljs                    # API base URL, env config
│       ├── routes.cljs                    # Reitit route definitions
│       ├── auth/
│       │   ├── events.cljs               # Re-frame events (login, logout, refresh)
│       │   ├── subs.cljs                 # Subscriptions (current-user, logged-in?)
│       │   ├── views.cljs                # Login page (Google SSO button)
│       │   └── interceptors.cljs         # Auth header interceptor for API calls
│       ├── api/
│       │   ├── client.cljs               # HTTP client wrapper (cljs-ajax)
│       │   └── endpoints.cljs            # All API endpoint definitions
│       ├── state/
│       │   ├── db.cljs                   # Initial app-db shape
│       │   ├── events.cljs               # Global events (notifications, loading)
│       │   └── subs.cljs                 # Global subscriptions
│       ├── ds/                            # Design System
│       │   ├── tokens.cljs               # Colors, spacing, breakpoints, typography
│       │   ├── theme.cljs                # Emotion theme provider
│       │   ├── layout.cljs               # Page shell, sidebar, header
│       │   ├── typography.cljs           # Heading, Text, Label components
│       │   ├── buttons.cljs              # Button, IconButton
│       │   ├── inputs.cljs               # Input, Select, DatePicker, FileUpload
│       │   ├── table.cljs                # DataTable with sort, pagination
│       │   ├── cards.cljs                # Card, StatCard, ProgressCard
│       │   ├── modal.cljs                # Modal, ConfirmDialog
│       │   ├── badge.cljs                # Badge, StatusBadge
│       │   ├── notifications.cljs        # NotificationBell, NotificationDropdown
│       │   ├── charts.cljs              # BarChart, LineChart wrappers (Recharts)
│       │   ├── progress.cljs            # ProgressBar, AchievementBar
│       │   ├── tabs.cljs                # TabGroup, Tab
│       │   ├── toast.cljs               # Toast notifications (success/error/warning)
│       │   └── empty_state.cljs         # Empty state illustrations
│       ├── views/
│       │   ├── ev/
│       │   │   ├── dashboard.cljs        # EV main dashboard
│       │   │   ├── deals_table.cljs      # Deals/policies table
│       │   │   ├── history.cljs          # Historical quarters view
│       │   │   ├── validation.cljs       # Deal validation during VALIDATING
│       │   │   ├── events.cljs           # EV-specific re-frame events
│       │   │   └── subs.cljs             # EV-specific subscriptions
│       │   ├── gerente/
│       │   │   ├── dashboard.cljs        # Manager team overview
│       │   │   ├── ev_detail.cljs        # Drill-down into EV (read-only)
│       │   │   ├── events.cljs
│       │   │   └── subs.cljs
│       │   ├── finance/
│       │   │   ├── dashboard.cljs        # Finance main dashboard
│       │   │   ├── saldo_devedor.cljs    # Saldo devedor por ano
│       │   │   ├── fluxo_caixa.cljs      # Cash flow chart
│       │   │   ├── orcado_realizado.cljs  # Budget vs actual
│       │   │   ├── approval.cljs         # Payment approval view
│       │   │   ├── export.cljs           # Export controls
│       │   │   ├── events.cljs
│       │   │   └── subs.cljs
│       │   ├── revops/
│       │   │   ├── dashboard.cljs        # Admin overview
│       │   │   ├── users.cljs            # CRUD users
│       │   │   ├── teams.cljs            # CRUD teams
│       │   │   ├── goals.cljs            # Manage goals (import + edit)
│       │   │   ├── commission_table.cljs  # Manage % table (versioned)
│       │   │   ├── financial_upload.cljs  # Upload XLSX flow
│       │   │   ├── appraisal.cljs        # Appraisal workflow control
│       │   │   ├── appraisal_review.cljs  # Review calculated values
│       │   │   ├── contestations.cljs    # Resolve EV contestations
│       │   │   ├── sync_status.cljs      # HubSpot sync monitor
│       │   │   ├── audit_log.cljs        # Audit log viewer
│       │   │   ├── settings.cljs         # Platform settings
│       │   │   ├── events.cljs
│       │   │   └── subs.cljs
│       │   └── shared/
│       │       ├── not_found.cljs        # 404 page
│       │       ├── no_role.cljs          # "Aguardando atribuição de role" page
│       │       └── loading.cljs          # Full-page loading spinner
├── test/
│   └── app/
│       ├── ds/
│       │   └── tokens_test.cljs
│       ├── auth/
│       │   └── events_test.cljs
│       ├── state/
│       │   └── subs_test.cljs
│       └── views/
│           └── ev/
│               └── dashboard_test.cljs
├── resources/
│   └── public/
│       ├── index.html
│       ├── favicon.ico
│       └── assets/
│           └── logo.svg
├── shadow-cljs.edn
├── package.json
├── Dockerfile
└── nginx.conf
```

---

## Chunk 1: Project Scaffold + Design System

### Task 1.1: Frontend Project Setup

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/shadow-cljs.edn`
- Create: `frontend/resources/public/index.html`
- Create: `frontend/src/app/core.cljs`
- Create: `frontend/src/app/config.cljs`

- [ ] **Step 1: Create frontend/package.json**

```json
{
  "name": "plataforma-comissoes-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "shadow-cljs watch app",
    "release": "shadow-cljs release app",
    "test": "shadow-cljs compile test && karma start --single-run",
    "test:watch": "shadow-cljs watch test",
    "lint": "clj-kondo --lint src/"
  },
  "devDependencies": {
    "shadow-cljs": "2.28.18",
    "karma": "6.4.4",
    "karma-chrome-launcher": "3.2.0",
    "karma-cljs-test": "0.1.0"
  },
  "dependencies": {
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "@emotion/react": "11.13.5",
    "@emotion/styled": "11.13.5",
    "recharts": "2.13.3",
    "dayjs": "1.11.13"
  }
}
```

- [ ] **Step 2: Create frontend/shadow-cljs.edn**

```clojure
{:source-paths ["src" "test"]

 :dependencies [[reagent "1.2.0"]
                [re-frame "1.4.3"]
                [metosin/reitit "0.7.2"]
                [metosin/reitit-frontend "0.7.2"]
                [cljs-ajax "0.8.4"]
                [day8.re-frame/http-fx "0.2.4"]
                [com.andrewmcveigh/cljs-time "0.5.2"]]

 :builds
 {:app
  {:target :browser
   :output-dir "resources/public/js/compiled"
   :asset-path "/js/compiled"

   :modules
   {:main {:init-fn app.core/init!}}

   :devtools
   {:http-root "resources/public"
    :http-port 8080
    :preloads [devtools.preload]}}

  :test
  {:target :karma
   :output-to "target/test/test.js"
   :ns-regexp "-test$"}}}
```

- [ ] **Step 3: Create frontend/resources/public/index.html**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Comissões — Pipo Saúde</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', sans-serif; background: #F7F6F3; color: #2B2B2B; }
    #app { min-height: 100vh; }
  </style>
</head>
<body>
  <div id="app">
    <div style="display:flex;justify-content:center;align-items:center;height:100vh;">
      Carregando...
    </div>
  </div>
  <script src="/js/compiled/main.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create frontend/src/app/config.cljs**

```clojure
(ns app.config)

(def api-base-url
  (if ^boolean goog.DEBUG
    "http://localhost:5000/api/v1"
    "/api/v1"))

(def google-client-id
  (or (.-GOOGLE_CLIENT_ID js/window) ""))

(def app-name "Comissões Pipo")
```

- [ ] **Step 5: Create frontend/src/app/core.cljs (minimal)**

```clojure
(ns app.core
  (:require [reagent.dom :as rdom]
            [re-frame.core :as rf]))

(defn app-root []
  [:div {:style {:display "flex"
                 :justify-content "center"
                 :align-items "center"
                 :height "100vh"
                 :font-family "'Inter', sans-serif"}}
   [:h1 "Plataforma de Comissões"]])

(defn ^:export init! []
  (rf/dispatch-sync [:initialize-db])
  (rdom/render [app-root]
               (.getElementById js/document "app")))
```

- [ ] **Step 6: Install dependencies and verify**

```bash
cd frontend && yarn install && yarn dev
```

Expected: App running on http://localhost:8080 showing "Plataforma de Comissões"

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold ClojureScript frontend with shadow-cljs, Reagent, Re-frame

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 1.2: Design System — Tokens

**Files:**
- Create: `frontend/src/app/ds/tokens.cljs`

- [ ] **Step 1: Create design tokens**

```clojure
(ns app.ds.tokens)

;; ============================================
;; COLORS — Pipo Saúde Commission Platform
;; ============================================

;; Brand
(def color-primary "#000000")
(def color-white "#FFFFFF")

;; Backgrounds
(def bg-main "#F7F6F3")
(def bg-surface "#EDECE7")
(def bg-card "#FFFFFF")

;; Grayscale — hierarchy
(def text-primary "#2B2B2B")
(def text-secondary "#6B6B6B")
(def text-disabled "#BDBDBD")
(def border-default "#E2E2E2")
(def bg-subtle "#F5F5F5")

;; Beige palette — surfaces
(def beige-700 "#6E6A63")
(def beige-500 "#C6B58A")
(def beige-300 "#E6DEC8")
(def beige-100 "#F3EFE4")

;; Overlay
(def overlay "rgba(0, 0, 0, 0.4)")

;; Semantic — feedback
(def success-default "#1FA971")
(def success-light "#D1FAE5")
(def success-dark "#15803D")

(def warning-default "#FFB703")
(def warning-light "#FEF3C7")
(def warning-dark "#B45309")

(def error-default "#EF4444")
(def error-light "#FEE2E2")
(def error-dark "#B91C1C")

;; Complementary — charts and illustrations only
(def blue-700 "#1E40AF")
(def blue-500 "#3B82F6")
(def purple-700 "#7C3AED")
(def purple-300 "#C4B5FD")
(def pink-500 "#F472B6")
(def pink-200 "#FBCFE8")
(def peach-400 "#FDBA74")
(def peach-200 "#FED7AA")

;; Chart color sequence
(def chart-colors [blue-500 purple-700 pink-500 peach-400 success-default warning-default])

;; ============================================
;; SPACING — 8px grid
;; ============================================

(def spacing
  {:0  "0"
   :1  "4px"
   :2  "8px"
   :3  "16px"
   :4  "24px"
   :5  "32px"
   :6  "48px"
   :7  "64px"
   :8  "128px"})

(defn sp [key] (get spacing key "0"))

;; Padding presets
(def padding
  {:xs   "4px"
   :sm   "8px"
   :md   "16px"
   :lg   "24px"
   :xl   "24px 24px"
   :card "24px"})

;; ============================================
;; TYPOGRAPHY
;; ============================================

(def font-family "'Inter', -apple-system, BlinkMacSystemFont, sans-serif")

(def font-sizes
  {:xs    "12px"
   :sm    "14px"
   :base  "16px"
   :lg    "18px"
   :xl    "20px"
   :2xl   "24px"
   :3xl   "30px"
   :4xl   "36px"})

(def font-weights
  {:regular  "400"
   :medium   "500"
   :semibold "600"
   :bold     "700"})

(def line-heights
  {:tight  "1.25"
   :normal "1.5"
   :loose  "1.75"})

;; ============================================
;; BREAKPOINTS
;; ============================================

(def breakpoints
  {:sm "576px"
   :md "768px"
   :lg "960px"
   :xl "1140px"})

;; ============================================
;; BORDERS & SHADOWS
;; ============================================

(def border-radius
  {:sm  "4px"
   :md  "8px"
   :lg  "12px"
   :xl  "16px"
   :full "9999px"})

(def shadows
  {:sm   "0 1px 2px rgba(0, 0, 0, 0.05)"
   :md   "0 4px 6px rgba(0, 0, 0, 0.07)"
   :lg   "0 10px 15px rgba(0, 0, 0, 0.1)"
   :card "0 1px 3px rgba(0, 0, 0, 0.08)"})

;; ============================================
;; TRANSITIONS
;; ============================================

(def transition-fast "150ms ease")
(def transition-default "250ms ease")
```

- [ ] **Step 2: Write token test**

Create `frontend/test/app/ds/tokens_test.cljs`:

```clojure
(ns app.ds.tokens-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.ds.tokens :as tokens]))

(deftest spacing-system-test
  (testing "spacing values are multiples of 4px"
    (is (= "8px" (tokens/sp :2)))
    (is (= "16px" (tokens/sp :3)))
    (is (= "0" (tokens/sp :0)))))

(deftest color-definitions-test
  (testing "primary colors are defined"
    (is (= "#000000" tokens/color-primary))
    (is (= "#F7F6F3" tokens/bg-main))
    (is (= "#2B2B2B" tokens/text-primary))))
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/ds/tokens.cljs frontend/test/
git commit -m "feat: add design system tokens — colors, spacing, typography, breakpoints

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 1.3: Design System — Core Components

**Files:**
- Create: `frontend/src/app/ds/typography.cljs`
- Create: `frontend/src/app/ds/buttons.cljs`
- Create: `frontend/src/app/ds/cards.cljs`
- Create: `frontend/src/app/ds/badge.cljs`
- Create: `frontend/src/app/ds/inputs.cljs`

- [ ] **Step 1: Create typography.cljs**

```clojure
(ns app.ds.typography
  (:require [app.ds.tokens :as t]))

(defn heading
  "Heading component. level: 1-4, children: content."
  [{:keys [level class]} & children]
  (let [tag (keyword (str "h" (or level 1)))
        styles {:h1 {:font-size (:4xl t/font-sizes) :font-weight (:bold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}
                :h2 {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}
                :h3 {:font-size (:2xl t/font-sizes) :font-weight (:semibold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}
                :h4 {:font-size (:xl t/font-sizes) :font-weight (:semibold t/font-weights) :line-height (:tight t/line-heights) :color t/text-primary :margin "0"}}]
    (into [tag {:style (get styles tag (:h1 styles))
                :class class}]
          children)))

(defn text
  "Body text. size: :xs :sm :base :lg, variant: :primary :secondary :disabled."
  [{:keys [size variant class style]} & children]
  (let [color (case (or variant :primary)
                :primary   t/text-primary
                :secondary t/text-secondary
                :disabled  t/text-disabled
                t/text-primary)
        font-size (get t/font-sizes (or size :base) (:base t/font-sizes))]
    (into [:p {:style (merge {:font-size font-size
                              :color color
                              :line-height (:normal t/line-heights)
                              :margin "0"
                              :font-family t/font-family}
                             style)
               :class class}]
          children)))

(defn label
  "Form label."
  [{:keys [required class]} & children]
  (into [:label {:style {:font-size (:sm t/font-sizes)
                         :font-weight (:medium t/font-weights)
                         :color t/text-primary
                         :margin-bottom "4px"
                         :display "block"}
                 :class class}]
        (concat children
                (when required
                  [[:span {:style {:color t/error-default :margin-left "4px"}} "*"]]))))
```

- [ ] **Step 2: Create buttons.cljs**

```clojure
(ns app.ds.buttons
  (:require [app.ds.tokens :as t]))

(defn button
  "Button component.
   variant: :primary :secondary :ghost :danger
   size: :sm :md :lg
   Props: on-click, disabled, loading, full-width"
  [{:keys [variant size on-click disabled loading full-width class]} & children]
  (let [v (or variant :primary)
        s (or size :md)
        base-style {:font-family t/font-family
                    :font-weight (:semibold t/font-weights)
                    :border-radius (:md t/border-radius)
                    :cursor (if disabled "not-allowed" "pointer")
                    :transition t/transition-fast
                    :display "inline-flex"
                    :align-items "center"
                    :justify-content "center"
                    :gap "8px"
                    :border "none"
                    :width (when full-width "100%")
                    :opacity (if disabled "0.5" "1")}
        size-styles {:sm {:font-size (:xs t/font-sizes) :padding "6px 12px" :height "32px"}
                     :md {:font-size (:sm t/font-sizes) :padding "8px 16px" :height "40px"}
                     :lg {:font-size (:base t/font-sizes) :padding "12px 24px" :height "48px"}}
        variant-styles {:primary   {:background t/color-primary :color t/color-white}
                        :secondary {:background t/bg-surface :color t/text-primary :border (str "1px solid " t/border-default)}
                        :ghost     {:background "transparent" :color t/text-primary}
                        :danger    {:background t/error-default :color t/color-white}}
        merged (merge base-style (get size-styles s) (get variant-styles v))]
    (into [:button {:style merged
                    :on-click (when-not (or disabled loading) on-click)
                    :disabled disabled
                    :class class}]
          (if loading
            [[:span "Carregando..."]]
            children))))
```

- [ ] **Step 3: Create cards.cljs**

```clojure
(ns app.ds.cards
  (:require [app.ds.tokens :as t]))

(defn card
  "Card container."
  [{:keys [padding class style]} & children]
  (into [:div {:style (merge {:background t/bg-card
                              :border-radius (:lg t/border-radius)
                              :padding (or padding (:card t/padding))
                              :box-shadow (:card t/shadows)}
                             style)
               :class class}]
        children))

(defn stat-card
  "Stat card with label, value, and optional change indicator.
   color: :default :success :warning :error"
  [{:keys [label value subtitle color]}]
  (let [accent (case (or color :default)
                 :success t/success-default
                 :warning t/warning-default
                 :error   t/error-default
                 t/color-primary)]
    [card {}
     [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
      [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase" :letter-spacing "0.05em" :font-weight (:medium t/font-weights)}} label]
      [:span {:style {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights) :color accent}} value]
      (when subtitle
        [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}} subtitle])]]))

(defn progress-card
  "Card with progress bar for achievement tracking."
  [{:keys [label current target percentage]}]
  (let [pct (or percentage (if (and current target (> target 0))
                             (* 100 (/ current target))
                             0))
        bar-color (cond
                    (>= pct 100) t/success-default
                    (>= pct 50)  t/warning-default
                    :else        t/error-default)]
    [card {}
     [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
      [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase" :letter-spacing "0.05em" :font-weight (:medium t/font-weights)}} label]
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "baseline"}}
       [:span {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights)}} (str (.toFixed pct 1) "%")]
       (when (and current target)
         [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
          (str "R$ " (.toLocaleString current "pt-BR") " / R$ " (.toLocaleString target "pt-BR"))])]
      ;; Progress bar
      [:div {:style {:width "100%" :height "8px" :background t/bg-subtle :border-radius (:full t/border-radius) :overflow "hidden"}}
       [:div {:style {:width (str (min pct 100) "%")
                      :height "100%"
                      :background bar-color
                      :border-radius (:full t/border-radius)
                      :transition t/transition-default}}]]]]))
```

- [ ] **Step 4: Create badge.cljs**

```clojure
(ns app.ds.badge
  (:require [app.ds.tokens :as t]))

(defn badge
  "Simple badge. variant: :default :success :warning :error :info."
  [{:keys [variant]} & children]
  (let [styles {:default {:bg t/bg-subtle :color t/text-secondary}
                :success {:bg t/success-light :color t/success-dark}
                :warning {:bg t/warning-light :color t/warning-dark}
                :error   {:bg t/error-light :color t/error-dark}
                :info    {:bg "#DBEAFE" :color t/blue-700}}
        s (get styles (or variant :default))]
    (into [:span {:style {:display "inline-flex"
                          :align-items "center"
                          :padding "2px 8px"
                          :font-size (:xs t/font-sizes)
                          :font-weight (:medium t/font-weights)
                          :border-radius (:full t/border-radius)
                          :background (:bg s)
                          :color (:color s)}}]
          children)))

(defn status-badge
  "Badge that maps commission/appraisal status to visual style."
  [{:keys [status]}]
  (let [config {"PROJECTED"     {:label "Projetado" :variant :default}
                "IN_PAYMENT"    {:label "Em pagamento" :variant :info}
                "SETTLED"       {:label "Quitado" :variant :success}
                "CANCELLED"     {:label "Cancelado" :variant :error}
                "DRAFT"         {:label "Rascunho" :variant :default}
                "CALCULATING"   {:label "Calculando" :variant :warning}
                "VALIDATING"    {:label "Validação" :variant :info}
                "REVIEWING"     {:label "Revisão" :variant :warning}
                "APPROVED"      {:label "Aprovado" :variant :success}
                "LOCKED"        {:label "Fechado" :variant :success}
                "PENDING"       {:label "Pendente" :variant :default}
                "CONTESTED"     {:label "Contestado" :variant :error}
                "RESOLVED"      {:label "Resolvido" :variant :success}
                "AUTO_APPROVED" {:label "Auto-aprovado" :variant :success}}
        {:keys [label variant]} (get config status {:label status :variant :default})]
    [badge {:variant variant} label]))
```

- [ ] **Step 5: Create inputs.cljs**

```clojure
(ns app.ds.inputs
  (:require [app.ds.tokens :as t]
            [app.ds.typography :as typo]))

(defn input
  "Text input.
   Props: value, on-change, placeholder, type, error, disabled, label, required."
  [{:keys [value on-change placeholder type error disabled label required name]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
   (when label
     [typo/label {:required required} label])
   [:input {:style {:font-family t/font-family
                    :font-size (:sm t/font-sizes)
                    :padding "8px 12px"
                    :height "40px"
                    :border (str "1px solid " (if error t/error-default t/border-default))
                    :border-radius (:md t/border-radius)
                    :background (if disabled t/bg-subtle t/bg-card)
                    :color (if disabled t/text-disabled t/text-primary)
                    :outline "none"
                    :transition t/transition-fast
                    :width "100%"}
            :type (or type "text")
            :value value
            :name name
            :placeholder placeholder
            :disabled disabled
            :on-change #(when on-change (on-change (.. % -target -value)))}]
   (when error
     [:span {:style {:font-size (:xs t/font-sizes) :color t/error-default}} error])])

(defn select
  "Select dropdown.
   options: [{:value \"x\" :label \"X\"} ...]"
  [{:keys [value on-change options label required disabled error]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
   (when label
     [typo/label {:required required} label])
   [:select {:style {:font-family t/font-family
                     :font-size (:sm t/font-sizes)
                     :padding "8px 12px"
                     :height "40px"
                     :border (str "1px solid " (if error t/error-default t/border-default))
                     :border-radius (:md t/border-radius)
                     :background t/bg-card
                     :color t/text-primary
                     :width "100%"
                     :cursor "pointer"}
             :value (or value "")
             :disabled disabled
             :on-change #(when on-change (on-change (.. % -target -value)))}
    (for [{:keys [value label]} options]
      ^{:key value}
      [:option {:value value} label])]])

(defn file-upload
  "File upload input for XLSX.
   Props: on-file, accept, label."
  [{:keys [on-file accept label]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
   (when label
     [typo/label {} label])
   [:label {:style {:display "flex"
                    :align-items "center"
                    :justify-content "center"
                    :padding "24px"
                    :border (str "2px dashed " t/border-default)
                    :border-radius (:lg t/border-radius)
                    :background t/bg-subtle
                    :cursor "pointer"
                    :transition t/transition-fast
                    :text-align "center"}}
    [:input {:type "file"
             :accept (or accept ".xlsx,.xls")
             :style {:display "none"}
             :on-change #(when on-file
                           (let [file (-> % .-target .-files (aget 0))]
                             (when file (on-file file))))}]
    [:div {:style {:display "flex" :flex-direction "column" :gap "4px" :align-items "center"}}
     [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}} "Clique ou arraste o arquivo aqui"]
     [:span {:style {:font-size (:xs t/font-sizes) :color t/text-disabled}} "Formatos: .xlsx, .xls"]]]])
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ds/
git commit -m "feat: add design system core components — typography, buttons, cards, badge, inputs

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 1.4: Design System — Table, Modal, Charts, Toast, Layout

**Files:**
- Create: `frontend/src/app/ds/table.cljs`
- Create: `frontend/src/app/ds/modal.cljs`
- Create: `frontend/src/app/ds/charts.cljs`
- Create: `frontend/src/app/ds/progress.cljs`
- Create: `frontend/src/app/ds/tabs.cljs`
- Create: `frontend/src/app/ds/toast.cljs`
- Create: `frontend/src/app/ds/notifications.cljs`
- Create: `frontend/src/app/ds/empty_state.cljs`
- Create: `frontend/src/app/ds/layout.cljs`

- [ ] **Step 1: Create table.cljs**

```clojure
(ns app.ds.table
  (:require [app.ds.tokens :as t]))

(defn data-table
  "Data table with sort, pagination.
   columns: [{:key :name :label \"Name\" :sortable true :render fn} ...]
   rows: [{:id 1 :name \"X\"} ...]
   Props: on-sort, sort-key, sort-order, page, total-pages, on-page-change"
  [{:keys [columns rows on-sort sort-key sort-order
           page total-pages on-page-change empty-message]}]
  [:div {:style {:overflow-x "auto"}}
   [:table {:style {:width "100%"
                    :border-collapse "collapse"
                    :font-size (:sm t/font-sizes)}}
    [:thead
     [:tr {:style {:border-bottom (str "2px solid " t/border-default)}}
      (for [{:keys [key label sortable width]} columns]
        ^{:key key}
        [:th {:style {:padding "12px 16px"
                      :text-align "left"
                      :font-weight (:semibold t/font-weights)
                      :color t/text-secondary
                      :font-size (:xs t/font-sizes)
                      :text-transform "uppercase"
                      :letter-spacing "0.05em"
                      :cursor (when sortable "pointer")
                      :width width
                      :user-select "none"}
              :on-click (when (and sortable on-sort)
                          #(on-sort key))}
         label
         (when (and sortable (= sort-key key))
           [:span {:style {:margin-left "4px"}}
            (if (= sort-order :asc) "↑" "↓")])])]]
    [:tbody
     (if (empty? rows)
       [:tr [:td {:col-span (count columns)
                  :style {:padding "48px 16px"
                          :text-align "center"
                          :color t/text-disabled}}
             (or empty-message "Nenhum dado encontrado")]]
       (for [row rows]
         ^{:key (or (:id row) (hash row))}
         [:tr {:style {:border-bottom (str "1px solid " t/bg-subtle)
                       :transition t/transition-fast}}
          (for [{:keys [key render]} columns]
            ^{:key (str (:id row) "-" key)}
            [:td {:style {:padding "12px 16px" :color t/text-primary}}
             (if render
               (render row)
               (get row key))])]))]]
   ;; Pagination
   (when (and page total-pages (> total-pages 1))
     [:div {:style {:display "flex"
                    :justify-content "space-between"
                    :align-items "center"
                    :padding "16px 0"}}
      [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
       (str "Página " page " de " total-pages)]
      [:div {:style {:display "flex" :gap "8px"}}
       [:button {:style {:padding "6px 12px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:md t/border-radius)
                         :background t/bg-card
                         :cursor (if (> page 1) "pointer" "not-allowed")
                         :opacity (if (> page 1) "1" "0.5")}
                 :disabled (<= page 1)
                 :on-click #(when (> page 1) (on-page-change (dec page)))}
        "Anterior"]
       [:button {:style {:padding "6px 12px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:md t/border-radius)
                         :background t/bg-card
                         :cursor (if (< page total-pages) "pointer" "not-allowed")
                         :opacity (if (< page total-pages) "1" "0.5")}
                 :disabled (>= page total-pages)
                 :on-click #(when (< page total-pages) (on-page-change (inc page)))}
        "Próxima"]]])])
```

- [ ] **Step 2: Create modal.cljs**

```clojure
(ns app.ds.modal
  (:require [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn modal
  "Modal dialog.
   Props: open?, on-close, title, size (:sm :md :lg)"
  [{:keys [open? on-close title size]} & children]
  (when open?
    [:div {:style {:position "fixed" :inset "0" :z-index "1000"
                   :display "flex" :align-items "center" :justify-content "center"}}
     ;; Overlay
     [:div {:style {:position "absolute" :inset "0" :background t/overlay}
            :on-click on-close}]
     ;; Content
     [:div {:style {:position "relative"
                    :background t/bg-card
                    :border-radius (:xl t/border-radius)
                    :box-shadow (:lg t/shadows)
                    :padding "32px"
                    :width (case (or size :md)
                             :sm "400px"
                             :md "560px"
                             :lg "720px"
                             "560px")
                    :max-height "90vh"
                    :overflow-y "auto"}}
      ;; Header
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "center" :margin-bottom "24px"}}
       [:h3 {:style {:font-size (:xl t/font-sizes) :font-weight (:semibold t/font-weights) :margin "0"}} title]
       [:button {:style {:background "none" :border "none" :cursor "pointer"
                         :font-size "20px" :color t/text-secondary :padding "4px"}
                 :on-click on-close} "✕"]]
      ;; Body
      (into [:div] children)]]))

(defn confirm-dialog
  "Confirmation dialog.
   Props: open?, on-close, on-confirm, title, message, confirm-label, variant"
  [{:keys [open? on-close on-confirm title message confirm-label variant]}]
  [modal {:open? open? :on-close on-close :title title :size :sm}
   [:p {:style {:color t/text-secondary :margin-bottom "24px"}} message]
   [:div {:style {:display "flex" :gap "12px" :justify-content "flex-end"}}
    [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
    [btn/button {:variant (or variant :primary) :on-click on-confirm}
     (or confirm-label "Confirmar")]]])
```

- [ ] **Step 3: Create charts.cljs (Recharts wrappers)**

```clojure
(ns app.ds.charts
  (:require [app.ds.tokens :as t]
            ["recharts" :as rc]))

(defn bar-chart
  "Bar chart wrapper.
   data: [{:name \"Jan\" :value 1000} ...]
   Props: x-key, bar-key, color, height"
  [{:keys [data x-key bar-key color height]}]
  [:> rc/ResponsiveContainer {:width "100%" :height (or height 300)}
   [:> rc/BarChart {:data (clj->js data)
                    :margin #js {:top 5 :right 20 :left 20 :bottom 5}}
    [:> rc/CartesianGrid {:strokeDasharray "3 3" :stroke t/bg-subtle}]
    [:> rc/XAxis {:dataKey (name (or x-key :name))
                  :tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/YAxis {:tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/Tooltip {:contentStyle #js {:borderRadius "8px" :border "none" :boxShadow (:md t/shadows)}}]
    [:> rc/Bar {:dataKey (name (or bar-key :value))
                :fill (or color (first t/chart-colors))
                :radius #js [4 4 0 0]}]]])

(defn line-chart
  "Line chart wrapper.
   data: [{:name \"Jan\" :actual 1000 :projected 1200} ...]
   lines: [{:key :actual :color \"blue\" :label \"Real\"} ...]"
  [{:keys [data lines x-key height]}]
  [:> rc/ResponsiveContainer {:width "100%" :height (or height 300)}
   [:> rc/LineChart {:data (clj->js data)
                     :margin #js {:top 5 :right 20 :left 20 :bottom 5}}
    [:> rc/CartesianGrid {:strokeDasharray "3 3" :stroke t/bg-subtle}]
    [:> rc/XAxis {:dataKey (name (or x-key :name))
                  :tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/YAxis {:tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/Tooltip {:contentStyle #js {:borderRadius "8px" :border "none" :boxShadow (:md t/shadows)}}]
    [:> rc/Legend]
    (for [{:keys [key color label dashed]} lines]
      ^{:key key}
      [:> rc/Line {:type "monotone"
                   :dataKey (name key)
                   :stroke (or color (first t/chart-colors))
                   :name label
                   :strokeWidth 2
                   :strokeDasharray (when dashed "5 5")
                   :dot false}])]])
```

- [ ] **Step 4: Create layout.cljs — page shell with sidebar**

```clojure
(ns app.ds.layout
  (:require [app.ds.tokens :as t]
            [re-frame.core :as rf]))

(defn sidebar-item
  [{:keys [label icon active? on-click]}]
  [:div {:style {:display "flex" :align-items "center" :gap "12px"
                 :padding "10px 16px"
                 :border-radius (:md t/border-radius)
                 :cursor "pointer"
                 :transition t/transition-fast
                 :background (if active? t/bg-surface "transparent")
                 :color (if active? t/text-primary t/text-secondary)
                 :font-weight (if active? (:semibold t/font-weights) (:regular t/font-weights))
                 :font-size (:sm t/font-sizes)}
         :on-click on-click}
   (when icon [:span icon])
   [:span label]])

(defn sidebar
  "Left sidebar navigation."
  [{:keys [items current-route user]}]
  [:nav {:style {:width "260px"
                 :min-height "100vh"
                 :background t/bg-card
                 :border-right (str "1px solid " t/border-default)
                 :padding "24px 16px"
                 :display "flex"
                 :flex-direction "column"
                 :gap "4px"}}
   ;; Logo / App name
   [:div {:style {:padding "0 16px 24px" :margin-bottom "8px"
                  :border-bottom (str "1px solid " t/border-default)}}
    [:h2 {:style {:font-size (:lg t/font-sizes) :font-weight (:bold t/font-weights) :color t/color-primary :margin "0"}}
     "Comissões"]
    [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Pipo Saúde"]]

   ;; Nav items
   (for [{:keys [key label icon route] :as item} items]
     ^{:key key}
     [sidebar-item {:label label
                    :icon icon
                    :active? (= key current-route)
                    :on-click #(rf/dispatch [:navigate route])}])

   ;; Spacer
   [:div {:style {:flex "1"}}]

   ;; User info at bottom
   (when user
     [:div {:style {:padding "16px"
                    :border-top (str "1px solid " t/border-default)
                    :display "flex"
                    :align-items "center"
                    :gap "12px"}}
      [:div {:style {:width "32px" :height "32px" :border-radius (:full t/border-radius)
                     :background t/bg-surface :display "flex" :align-items "center" :justify-content "center"
                     :font-size (:xs t/font-sizes) :font-weight (:semibold t/font-weights) :color t/text-secondary}}
       (-> (:name user) first str .toUpperCase)]
      [:div {:style {:display "flex" :flex-direction "column"}}
       [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:medium t/font-weights)}} (:name user)]
       [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} (:role user)]]])])

(defn header
  "Top header with notification bell and breadcrumb."
  [{:keys [title subtitle]} & children]
  [:header {:style {:display "flex"
                    :justify-content "space-between"
                    :align-items "center"
                    :padding "24px 32px"
                    :background t/bg-card
                    :border-bottom (str "1px solid " t/border-default)}}
   [:div
    [:h1 {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights) :margin "0" :color t/text-primary}} title]
    (when subtitle
      [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}} subtitle])]
   (into [:div {:style {:display "flex" :align-items "center" :gap "16px"}}] children)])

(defn page-shell
  "Main page layout: sidebar + header + content."
  [{:keys [sidebar-items current-route user title subtitle header-actions]} & children]
  [:div {:style {:display "flex" :min-height "100vh" :background t/bg-main}}
   ;; Sidebar
   [sidebar {:items sidebar-items :current-route current-route :user user}]
   ;; Main content
   [:div {:style {:flex "1" :display "flex" :flex-direction "column"}}
    [header {:title title :subtitle subtitle}
     header-actions]
    (into [:main {:style {:flex "1" :padding "32px" :overflow-y "auto"}}]
          children)]])
```

- [ ] **Step 5: Create toast.cljs, notifications.cljs, tabs.cljs, progress.cljs, empty_state.cljs**

(Smaller components, following the same pattern as above. Each one is a pure Reagent component using tokens.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ds/
git commit -m "feat: add design system — table, modal, charts, layout shell, toast, tabs

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 2: State Management + Auth + Routing

### Task 2.1: Re-frame App DB + Global State

**Files:**
- Create: `frontend/src/app/state/db.cljs`
- Create: `frontend/src/app/state/events.cljs`
- Create: `frontend/src/app/state/subs.cljs`

- [ ] **Step 1: Define initial app-db shape**

```clojure
;; frontend/src/app/state/db.cljs
(ns app.state.db)

(def initial-db
  {:auth {:user nil            ;; {:id, :email, :name, :role, :team_id}
          :access-token nil
          :refresh-token nil
          :loading? false
          :error nil}

   :notifications {:items []
                   :unread-count 0
                   :loading? false}

   :ui {:sidebar-collapsed? false
        :active-modal nil
        :toast nil}

   ;; Page-specific data loaded on demand
   :policies {:items []
              :meta nil
              :loading? false
              :filters {:quarter nil :year nil :status nil}}

   :commissions {:items []
                 :summary nil
                 :projection []
                 :loading? false}

   :goals {:items []
           :loading? false}

   :appraisal {:current nil    ;; Active appraisal being worked on
               :list []
               :loading? false}

   :validations {:items []
                 :loading? false}

   :finance {:dashboard nil
             :loading? false}

   :admin {:users []
           :teams []
           :commission-table {:current-version nil :rows []}
           :settings {}
           :sync-status nil
           :audit-log {:items [] :meta nil}}})
```

- [ ] **Step 2: Create global events**

```clojure
;; frontend/src/app/state/events.cljs
(ns app.state.events
  (:require [re-frame.core :as rf]
            [app.state.db :as db]))

(rf/reg-event-db
 :initialize-db
 (fn [_ _]
   db/initial-db))

;; UI events
(rf/reg-event-db
 :ui/show-toast
 (fn [db [_ {:keys [type message duration]}]]
   (assoc-in db [:ui :toast] {:type type :message message :duration (or duration 3000)})))

(rf/reg-event-db
 :ui/clear-toast
 (fn [db _]
   (assoc-in db [:ui :toast] nil)))

(rf/reg-event-db
 :ui/show-modal
 (fn [db [_ modal-id data]]
   (assoc-in db [:ui :active-modal] {:id modal-id :data data})))

(rf/reg-event-db
 :ui/close-modal
 (fn [db _]
   (assoc-in db [:ui :active-modal] nil)))

;; Navigation
(rf/reg-event-fx
 :navigate
 (fn [{:keys [db]} [_ route]]
   ;; Will be wired to reitit
   {:db db
    :navigate! route}))
```

- [ ] **Step 3: Create global subscriptions**

```clojure
;; frontend/src/app/state/subs.cljs
(ns app.state.subs
  (:require [re-frame.core :as rf]))

;; Auth
(rf/reg-sub :auth/user (fn [db _] (get-in db [:auth :user])))
(rf/reg-sub :auth/role (fn [db _] (get-in db [:auth :user :role])))
(rf/reg-sub :auth/logged-in? (fn [db _] (some? (get-in db [:auth :access-token]))))
(rf/reg-sub :auth/loading? (fn [db _] (get-in db [:auth :loading?])))

;; UI
(rf/reg-sub :ui/toast (fn [db _] (get-in db [:ui :toast])))
(rf/reg-sub :ui/active-modal (fn [db _] (get-in db [:ui :active-modal])))

;; Notifications
(rf/reg-sub :notifications/items (fn [db _] (get-in db [:notifications :items])))
(rf/reg-sub :notifications/unread-count (fn [db _] (get-in db [:notifications :unread-count])))
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/state/
git commit -m "feat: add Re-frame app-db, global events, and subscriptions

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 2.2: API Client + Auth Interceptor

**Files:**
- Create: `frontend/src/app/api/client.cljs`
- Create: `frontend/src/app/api/endpoints.cljs`
- Create: `frontend/src/app/auth/events.cljs`
- Create: `frontend/src/app/auth/subs.cljs`
- Create: `frontend/src/app/auth/interceptors.cljs`
- Create: `frontend/src/app/auth/views.cljs`

- [ ] **Step 1: Create API client**

```clojure
;; frontend/src/app/api/client.cljs
(ns app.api.client
  (:require [ajax.core :as ajax]
            [re-frame.core :as rf]
            [app.config :as config]))

(defn api-url [path]
  (str config/api-base-url path))

(rf/reg-fx
 :http
 (fn [{:keys [method url body on-success on-failure headers]}]
   (let [token @(rf/subscribe [:auth/access-token-raw])
         default-headers (cond-> {"Content-Type" "application/json"}
                           token (assoc "Authorization" (str "Bearer " token)))]
     (ajax/ajax-request
      {:uri (api-url url)
       :method method
       :headers (merge default-headers headers)
       :params body
       :format (ajax/json-request-format)
       :response-format (ajax/json-response-format {:keywords? true})
       :handler (fn [[ok response]]
                  (if ok
                    (when on-success (rf/dispatch (conj on-success response)))
                    (do
                      ;; Auto-refresh on 401
                      (when (= 401 (:status response))
                        (rf/dispatch [:auth/try-refresh]))
                      (when on-failure (rf/dispatch (conj on-failure response))))))}))))

;; Subscription for raw token (used by :http effect)
(rf/reg-sub :auth/access-token-raw (fn [db _] (get-in db [:auth :access-token])))
```

- [ ] **Step 2: Create auth events**

```clojure
;; frontend/src/app/auth/events.cljs
(ns app.auth.events
  (:require [re-frame.core :as rf]))

(rf/reg-event-fx
 :auth/google-login
 (fn [{:keys [db]} [_ google-code]]
   {:db (assoc-in db [:auth :loading?] true)
    :http {:method :post
           :url "/auth/google"
           :body {:code google-code}
           :on-success [:auth/login-success]
           :on-failure [:auth/login-failure]}}))

(rf/reg-event-fx
 :auth/login-success
 (fn [{:keys [db]} [_ response]]
   (let [data (:data response)]
     {:db (-> db
              (assoc-in [:auth :user] (:user data))
              (assoc-in [:auth :access-token] (:access_token data))
              (assoc-in [:auth :refresh-token] (:refresh_token data))
              (assoc-in [:auth :loading?] false)
              (assoc-in [:auth :error] nil))
      :navigate! (case (get-in data [:user :role])
                   "ADMIN"   :revops/dashboard
                   "FINANCE" :finance/dashboard
                   "GERENTE" :gerente/dashboard
                   "EV"      :ev/dashboard
                   "CN"      :ev/dashboard
                   :no-role)})))

(rf/reg-event-db
 :auth/login-failure
 (fn [db [_ error]]
   (-> db
       (assoc-in [:auth :loading?] false)
       (assoc-in [:auth :error] "Falha no login. Tente novamente."))))

(rf/reg-event-fx
 :auth/try-refresh
 (fn [{:keys [db]} _]
   (let [refresh-token (get-in db [:auth :refresh-token])]
     (when refresh-token
       {:http {:method :post
               :url "/auth/refresh"
               :body {:refresh_token refresh-token}
               :on-success [:auth/refresh-success]
               :on-failure [:auth/logout]}}))))

(rf/reg-event-db
 :auth/refresh-success
 (fn [db [_ response]]
   (assoc-in db [:auth :access-token] (get-in response [:data :access_token]))))

(rf/reg-event-fx
 :auth/logout
 (fn [{:keys [db]} _]
   {:db (-> db
            (assoc-in [:auth :user] nil)
            (assoc-in [:auth :access-token] nil)
            (assoc-in [:auth :refresh-token] nil))
    :navigate! :login}))
```

- [ ] **Step 3: Create login view**

```clojure
;; frontend/src/app/auth/views.cljs
(ns app.auth.views
  (:require [re-frame.core :as rf]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]
            [app.config :as config]))

(defn login-page []
  (let [loading? @(rf/subscribe [:auth/loading?])
        error @(rf/subscribe [:auth/error])]
    [:div {:style {:min-height "100vh"
                   :display "flex"
                   :align-items "center"
                   :justify-content "center"
                   :background t/bg-main}}
     [:div {:style {:background t/bg-card
                    :padding "48px"
                    :border-radius (:xl t/border-radius)
                    :box-shadow (:lg t/shadows)
                    :text-align "center"
                    :width "400px"}}
      [:h1 {:style {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights)
                    :color t/color-primary :margin-bottom "8px"}}
       "Comissões"]
      [:p {:style {:color t/text-secondary :margin-bottom "32px" :font-size (:sm t/font-sizes)}}
       "Plataforma de gestão de comissões — Pipo Saúde"]
      (when error
        [:div {:style {:background t/error-light :color t/error-dark
                       :padding "12px" :border-radius (:md t/border-radius)
                       :margin-bottom "16px" :font-size (:sm t/font-sizes)}}
         error])
      [btn/button {:variant :primary
                   :size :lg
                   :full-width true
                   :loading loading?
                   :on-click #(js/console.log "Google SSO — will integrate with gapi")}
       "Entrar com Google"]]]))
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/api/ frontend/src/app/auth/
git commit -m "feat: add API client with JWT interceptor, auth events, and login page

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 2.3: Routing

**Files:**
- Create: `frontend/src/app/routes.cljs`
- Modify: `frontend/src/app/core.cljs`

- [ ] **Step 1: Define routes**

```clojure
;; frontend/src/app/routes.cljs
(ns app.routes
  (:require [reitit.frontend :as rf-router]
            [reitit.frontend.easy :as rfe]
            [re-frame.core :as rf]))

(def routes
  (rf-router/router
   [["/" {:name :home}]
    ["/login" {:name :login}]
    ["/no-role" {:name :no-role}]

    ;; EV / CN
    ["/ev"
     ["/dashboard" {:name :ev/dashboard :role #{:EV :CN :ADMIN}}]
     ["/history" {:name :ev/history :role #{:EV :CN :ADMIN}}]
     ["/validation" {:name :ev/validation :role #{:EV :CN :ADMIN}}]]

    ;; Gerente
    ["/gerente"
     ["/dashboard" {:name :gerente/dashboard :role #{:GERENTE :ADMIN}}]
     ["/ev/:ev-id" {:name :gerente/ev-detail :role #{:GERENTE :ADMIN}}]]

    ;; Finance
    ["/finance"
     ["/dashboard" {:name :finance/dashboard :role #{:FINANCE :ADMIN}}]
     ["/approval" {:name :finance/approval :role #{:FINANCE :ADMIN}}]]

    ;; RevOps (Admin)
    ["/admin"
     ["/dashboard" {:name :revops/dashboard :role #{:ADMIN}}]
     ["/users" {:name :revops/users :role #{:ADMIN}}]
     ["/teams" {:name :revops/teams :role #{:ADMIN}}]
     ["/goals" {:name :revops/goals :role #{:ADMIN}}]
     ["/commission-table" {:name :revops/commission-table :role #{:ADMIN}}]
     ["/financial" {:name :revops/financial :role #{:ADMIN}}]
     ["/appraisal" {:name :revops/appraisal :role #{:ADMIN}}]
     ["/appraisal/:id/review" {:name :revops/appraisal-review :role #{:ADMIN}}]
     ["/contestations" {:name :revops/contestations :role #{:ADMIN}}]
     ["/sync" {:name :revops/sync-status :role #{:ADMIN}}]
     ["/audit" {:name :revops/audit-log :role #{:ADMIN}}]
     ["/settings" {:name :revops/settings :role #{:ADMIN}}]]]))

(defn init-routing! []
  (rfe/start!
   routes
   (fn [match]
     (when match
       (rf/dispatch [:route/changed match])))
   {:use-fragment false}))

;; Re-frame events for routing
(rf/reg-event-db
 :route/changed
 (fn [db [_ match]]
   (assoc db :current-route match)))

(rf/reg-sub
 :current-route
 (fn [db _] (:current-route db)))

(rf/reg-sub
 :current-route-name
 :<- [:current-route]
 (fn [route _]
   (get-in route [:data :name])))

;; Navigate effect
(rf/reg-fx
 :navigate!
 (fn [route-name]
   (rfe/push-state route-name)))
```

- [ ] **Step 2: Update core.cljs with routing + role-based view switching**

```clojure
(ns app.core
  (:require [reagent.dom :as rdom]
            [re-frame.core :as rf]
            [app.state.events]
            [app.state.subs]
            [app.auth.events]
            [app.routes :as routes]
            [app.auth.views :as auth-views]
            [app.views.ev.dashboard :as ev-dashboard]
            [app.views.gerente.dashboard :as gerente-dashboard]
            [app.views.finance.dashboard :as finance-dashboard]
            [app.views.revops.dashboard :as revops-dashboard]
            [app.views.shared.not_found :as not-found]
            [app.views.shared.no_role :as no-role-view]))

(defn route-view []
  (let [route-name @(rf/subscribe [:current-route-name])
        logged-in? @(rf/subscribe [:auth/logged-in?])]
    (cond
      (not logged-in?)
      [auth-views/login-page]

      (= route-name :no-role)
      [no-role-view/no-role-page]

      :else
      (case route-name
        ;; EV
        :ev/dashboard       [ev-dashboard/page]
        :ev/history         [ev-dashboard/history-page]
        :ev/validation      [ev-dashboard/validation-page]
        ;; Gerente
        :gerente/dashboard  [gerente-dashboard/page]
        :gerente/ev-detail  [gerente-dashboard/ev-detail-page]
        ;; Finance
        :finance/dashboard  [finance-dashboard/page]
        :finance/approval   [finance-dashboard/approval-page]
        ;; RevOps
        :revops/dashboard   [revops-dashboard/page]
        ;; ... all other revops routes
        ;; Default
        [not-found/page]))))

(defn app-root []
  [route-view])

(defn ^:export init! []
  (rf/dispatch-sync [:initialize-db])
  (routes/init-routing!)
  (rdom/render [app-root]
               (.getElementById js/document "app")))
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/routes.cljs frontend/src/app/core.cljs
git commit -m "feat: add Reitit routing with role-based view switching

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 3: Views — EV + Gerente

### Task 3.1: EV Dashboard

**Files:**
- Create: `frontend/src/app/views/ev/events.cljs`
- Create: `frontend/src/app/views/ev/subs.cljs`
- Create: `frontend/src/app/views/ev/dashboard.cljs`
- Create: `frontend/src/app/views/ev/deals_table.cljs`
- Create: `frontend/src/app/views/ev/validation.cljs`
- Create: `frontend/src/app/views/ev/history.cljs`

- [ ] **Step 1: Create EV events (fetch data from API)**

```clojure
;; frontend/src/app/views/ev/events.cljs
(ns app.views.ev.events
  (:require [re-frame.core :as rf]))

(rf/reg-event-fx
 :ev/fetch-dashboard
 (fn [{:keys [db]} _]
   {:db (assoc-in db [:commissions :loading?] true)
    :http {:method :get
           :url "/commissions/summary"
           :on-success [:ev/dashboard-loaded]
           :on-failure [:ev/dashboard-error]}}))

(rf/reg-event-db
 :ev/dashboard-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:commissions :summary] (:data response))
       (assoc-in [:commissions :loading?] false))))

(rf/reg-event-fx
 :ev/fetch-policies
 (fn [{:keys [db]} [_ params]]
   {:db (assoc-in db [:policies :loading?] true)
    :http {:method :get
           :url (str "/policies?" (js/URLSearchParams. (clj->js params)))
           :on-success [:ev/policies-loaded]
           :on-failure [:ev/policies-error]}}))

(rf/reg-event-db
 :ev/policies-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:policies :items] (:data response))
       (assoc-in [:policies :meta] (:meta response))
       (assoc-in [:policies :loading?] false))))

(rf/reg-event-fx
 :ev/fetch-projection
 (fn [{:keys [db]} _]
   {:http {:method :get
           :url "/commissions/projection"
           :on-success [:ev/projection-loaded]}}))

(rf/reg-event-db
 :ev/projection-loaded
 (fn [db [_ response]]
   (assoc-in db [:commissions :projection] (:data response))))
```

- [ ] **Step 2: Create EV subscriptions**

```clojure
;; frontend/src/app/views/ev/subs.cljs
(ns app.views.ev.subs
  (:require [re-frame.core :as rf]))

(rf/reg-sub :ev/summary (fn [db _] (get-in db [:commissions :summary])))
(rf/reg-sub :ev/policies (fn [db _] (get-in db [:policies :items])))
(rf/reg-sub :ev/policies-meta (fn [db _] (get-in db [:policies :meta])))
(rf/reg-sub :ev/policies-loading? (fn [db _] (get-in db [:policies :loading?])))
(rf/reg-sub :ev/projection (fn [db _] (get-in db [:commissions :projection])))
(rf/reg-sub :ev/validations (fn [db _] (get-in db [:validations :items])))
```

- [ ] **Step 3: Create EV dashboard page**

```clojure
;; frontend/src/app/views/ev/dashboard.cljs
(ns app.views.ev.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.tokens :as t]
            [app.ds.charts :as charts]
            [app.views.ev.deals-table :as deals-table]
            [app.views.ev.events]
            [app.views.ev.subs]))

(def sidebar-items
  [{:key :ev/dashboard :label "Dashboard" :icon "📊" :route :ev/dashboard}
   {:key :ev/history :label "Histórico" :icon "📅" :route :ev/history}
   {:key :ev/validation :label "Validação" :icon "✅" :route :ev/validation}])

(defn dashboard-content []
  (let [summary @(rf/subscribe [:ev/summary])
        projection @(rf/subscribe [:ev/projection])]
    [:div {:style {:display "flex" :flex-direction "column" :gap "24px"}}
     ;; Stat cards row
     [:div {:style {:display "grid" :grid-template-columns "repeat(3, 1fr)" :gap "16px"}}
      [cards/stat-card {:label "Saldo a receber (estimado)"
                        :value (str "R$ " (or (:balance_estimated summary) "0"))
                        :color :default}]
      [cards/progress-card {:label "Atingimento no trimestre"
                            :current (js/parseFloat (or (:mrr_sold summary) "0"))
                            :target (js/parseFloat (or (:mrr_target summary) "1"))
                            :percentage (js/parseFloat (or (:achievement_pct summary) "0"))}]
      [cards/stat-card {:label "Meta MRR"
                        :value (str "R$ " (or (:mrr_target summary) "0"))
                        :subtitle (str "Q" (:current_quarter summary) "/" (:current_year summary))}]]

     ;; Projection chart
     [cards/card {}
      [:h3 {:style {:font-size (:lg t/font-sizes) :font-weight (:semibold t/font-weights) :margin-bottom "16px"}} "Projeção 12 meses"]
      [charts/bar-chart {:data (or projection [])
                         :x-key :month
                         :bar-key :projected
                         :height 250}]]

     ;; Deals table
     [deals-table/component]]))

(defn page []
  (rf/dispatch [:ev/fetch-dashboard])
  (rf/dispatch [:ev/fetch-policies {}])
  (rf/dispatch [:ev/fetch-projection])
  (let [user @(rf/subscribe [:auth/user])
        route @(rf/subscribe [:current-route-name])]
    [layout/page-shell {:sidebar-items sidebar-items
                        :current-route route
                        :user user
                        :title "Dashboard"
                        :subtitle (str "Q" (:current_quarter @(rf/subscribe [:ev/summary])) " "
                                       (:current_year @(rf/subscribe [:ev/summary])))}
     [dashboard-content]]))
```

- [ ] **Step 4: Create deals table component**

```clojure
;; frontend/src/app/views/ev/deals_table.cljs
(ns app.views.ev.deals-table
  (:require [re-frame.core :as rf]
            [app.ds.table :as table]
            [app.ds.badge :as badge]
            [app.ds.cards :as cards]
            [app.ds.tokens :as t]))

(def columns
  [{:key :client_name :label "Cliente" :sortable true}
   {:key :benefit_type :label "Benefício" :sortable true}
   {:key :segment :label "Segmento" :sortable true :width "80px"}
   {:key :mrr_for_commission :label "MRR" :sortable true
    :render (fn [row] (str "R$ " (:mrr_for_commission row)))}
   {:key :commission_pct :label "%" :width "60px"
    :render (fn [row] (when (:commission_pct row) (str (* 100 (js/parseFloat (:commission_pct row))) "%")))}
   {:key :monthly_estimated :label "Comissão/mês" :sortable true
    :render (fn [row] (str "R$ " (or (:monthly_estimated row) "-")))}
   {:key :installments_paid :label "Parcelas" :width "80px"
    :render (fn [row] (str (:installments_paid row) "/12"))}
   {:key :commission_status :label "Status" :width "120px"
    :render (fn [row] [badge/status-badge {:status (:commission_status row)}])}])

(defn component []
  (let [policies @(rf/subscribe [:ev/policies])
        meta @(rf/subscribe [:ev/policies-meta])
        loading? @(rf/subscribe [:ev/policies-loading?])]
    [cards/card {}
     [:h3 {:style {:font-size (:lg t/font-sizes) :font-weight (:semibold t/font-weights) :margin-bottom "16px"}} "Meus Deals"]
     [table/data-table {:columns columns
                        :rows policies
                        :page (:page meta)
                        :total-pages (:total_pages meta)
                        :on-page-change #(rf/dispatch [:ev/fetch-policies {:page %}])
                        :empty-message "Nenhum deal encontrado"}]]))
```

- [ ] **Step 5: Create validation page**

```clojure
;; frontend/src/app/views/ev/validation.cljs
(ns app.views.ev.validation
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.buttons :as btn]
            [app.ds.badge :as badge]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]))

(defn validation-item [{:keys [validation]}]
  (let [contest-open? (r/atom false)
        comment (r/atom "")]
    (fn [{:keys [validation]}]
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"
                     :padding "16px" :border-bottom (str "1px solid " t/bg-subtle)}}
       [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
        [:span {:style {:font-weight (:medium t/font-weights)}} (:client_name validation)]
        [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
         (str (:benefit_type validation) " | " (:segment validation) " | MRR R$ " (:mrr validation))]
        [:span {:style {:font-size (:sm t/font-sizes)}}
         (str "Comissão: R$ " (:monthly_actual validation) "/mês (" (:commission_pct validation) "%)")]]
       [:div {:style {:display "flex" :gap "8px" :align-items "center"}}
        [badge/status-badge {:status (:status validation)}]
        (when (= (:status validation) "PENDING")
          [:<>
           [btn/button {:variant :primary :size :sm
                        :on-click #(rf/dispatch [:ev/approve-validation (:id validation)])}
            "Aprovar"]
           [btn/button {:variant :danger :size :sm
                        :on-click #(reset! contest-open? true)}
            "Contestar"]])
        [modal/modal {:open? @contest-open? :on-close #(reset! contest-open? false)
                      :title "Contestar deal" :size :sm}
         [inputs/input {:label "Motivo da contestação" :required true
                        :value @comment
                        :on-change #(reset! comment %)}]
         [:div {:style {:display "flex" :justify-content "flex-end" :gap "8px" :margin-top "16px"}}
          [btn/button {:variant :secondary :on-click #(reset! contest-open? false)} "Cancelar"]
          [btn/button {:variant :danger
                       :disabled (empty? @comment)
                       :on-click (fn []
                                   (rf/dispatch [:ev/contest-validation (:id validation) @comment])
                                   (reset! contest-open? false)
                                   (reset! comment ""))}
           "Enviar contestação"]]]]])))

(defn validation-page []
  (let [validations @(rf/subscribe [:ev/validations])
        approved-count (count (filter #(#{"APPROVED" "AUTO_APPROVED"} (:status %)) validations))
        total (count validations)]
    [layout/page-shell {:sidebar-items (deref (rf/subscribe [:ev/sidebar-items]))
                        :current-route :ev/validation
                        :user @(rf/subscribe [:auth/user])
                        :title "Validação de Deals"
                        :subtitle (str approved-count " de " total " validados")}
     [cards/card {}
      (for [v validations]
        ^{:key (:id v)}
        [validation-item {:validation v}])]]))
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/views/ev/
git commit -m "feat: add EV views — dashboard, deals table, projection chart, validation flow

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 3.2: Gerente View

**Files:**
- Create: `frontend/src/app/views/gerente/dashboard.cljs`
- Create: `frontend/src/app/views/gerente/ev_detail.cljs`
- Create: `frontend/src/app/views/gerente/events.cljs`
- Create: `frontend/src/app/views/gerente/subs.cljs`

- [ ] **Step 1: Create gerente dashboard (team consolidated)**

The gerente view reuses EV components in read-only mode. Dashboard shows a table of team members with summary stats. Clicking an EV drills down to their full dashboard (read-only).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/views/gerente/
git commit -m "feat: add Gerente views — team consolidated dashboard, EV drill-down

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 4: Views — Finance + RevOps

### Task 4.1: Finance Dashboard

**Files:**
- Create: `frontend/src/app/views/finance/dashboard.cljs`
- Create: `frontend/src/app/views/finance/saldo_devedor.cljs`
- Create: `frontend/src/app/views/finance/fluxo_caixa.cljs`
- Create: `frontend/src/app/views/finance/orcado_realizado.cljs`
- Create: `frontend/src/app/views/finance/approval.cljs`
- Create: `frontend/src/app/views/finance/export.cljs`
- Create: `frontend/src/app/views/finance/events.cljs`
- Create: `frontend/src/app/views/finance/subs.cljs`

- [ ] **Step 1: Create finance events and subs**

Fetches `/finance/dashboard` which returns saldo devedor total, separação por ano (dinâmica), fluxo de caixa mensal, orçado vs realizado.

- [ ] **Step 2: Create finance dashboard page**

Uses stat-cards for saldo devedor total + per-year breakdown. Line chart for cash flow. Bar chart for budget vs actual. Table with per-EV breakdown and drill-down.

- [ ] **Step 3: Create approval page**

Shows appraisals in APPROVED status. Buttons "Liberar Pagamento" and "Devolver pro RevOps". Consolidado view with total per EV.

- [ ] **Step 4: Create export component**

Dropdown with format selection (Excel, CSV, PDF) + filter panel (period, EV, team, status). Triggers download via `/finance/export?format=xlsx&...`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/views/finance/
git commit -m "feat: add Finance views — saldo devedor, fluxo caixa, orçado vs realizado, approval, export

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 4.2: RevOps Admin Views

**Files:**
- Create all files in `frontend/src/app/views/revops/`

- [ ] **Step 1: Admin dashboard** — overview of active appraisal status, recent sync, pending actions

- [ ] **Step 2: Users CRUD** — table of users, create/edit modal with role select, team assignment

- [ ] **Step 3: Teams CRUD** — table, create/edit with leader select

- [ ] **Step 4: Goals management** — table filtered by quarter/year, inline edit, XLSX import button

- [ ] **Step 5: Commission table management** — current version display as 3×3 grid, "Criar nova versão" creates version+1 with editable values

- [ ] **Step 6: Financial upload** — file-upload component → preview table (new/updated/errors) → confirm button

- [ ] **Step 7: Appraisal workflow control** — step-by-step UI:
  - DRAFT: "Iniciar Apuração" button
  - CALCULATING: progress indicator, then "Liberar para Validação"
  - VALIDATING: progress of EVs, deadline countdown
  - REVIEWING: contestation list with resolve buttons
  - APPROVED/LOCKED: status display

- [ ] **Step 8: Sync status** — last sync timestamp, created/updated/error counts, manual "Sync Now" button

- [ ] **Step 9: Audit log viewer** — filterable table: date range, table, user, action

- [ ] **Step 10: Settings** — key-value editor: validation deadline days, sync interval, notification toggles

- [ ] **Step 11: Commit**

```bash
git add frontend/src/app/views/revops/
git commit -m "feat: add RevOps admin views — users, teams, goals, commission table, financial upload, appraisal workflow, sync, audit, settings

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

## Chunk 5: Shared + Notifications + Docker

### Task 5.1: Shared Views

**Files:**
- Create: `frontend/src/app/views/shared/not_found.cljs`
- Create: `frontend/src/app/views/shared/no_role.cljs`
- Create: `frontend/src/app/views/shared/loading.cljs`

- [ ] **Step 1: Create 404, no-role, and loading pages**

Simple, clean pages using design system tokens. "Aguardando atribuição de acesso" for no-role.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/views/shared/
git commit -m "feat: add shared views — 404, no-role, loading

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 5.2: Notification System (Frontend)

**Files:**
- Create: `frontend/src/app/ds/notifications.cljs` (bell + dropdown)
- Modify: `frontend/src/app/ds/layout.cljs` (add bell to header)

- [ ] **Step 1: Create notification bell + dropdown component**

```clojure
;; frontend/src/app/ds/notifications.cljs
(ns app.ds.notifications
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.tokens :as t]))

(defn notification-bell []
  (let [open? (r/atom false)
        unread @(rf/subscribe [:notifications/unread-count])
        items @(rf/subscribe [:notifications/items])]
    [:div {:style {:position "relative"}}
     ;; Bell button
     [:button {:style {:background "none" :border "none" :cursor "pointer"
                       :position "relative" :padding "8px"}
               :on-click #(do (swap! open? not)
                              (when-not @open?
                                (rf/dispatch [:notifications/fetch])))}
      [:span {:style {:font-size "20px"}} "🔔"]
      (when (> unread 0)
        [:span {:style {:position "absolute" :top "4px" :right "4px"
                        :background t/error-default :color t/color-white
                        :font-size "10px" :font-weight (:bold t/font-weights)
                        :width "18px" :height "18px" :border-radius (:full t/border-radius)
                        :display "flex" :align-items "center" :justify-content "center"}}
         unread])]
     ;; Dropdown
     (when @open?
       [:div {:style {:position "absolute" :right "0" :top "40px"
                      :width "360px" :background t/bg-card
                      :border-radius (:lg t/border-radius)
                      :box-shadow (:lg t/shadows)
                      :z-index "100" :max-height "400px" :overflow-y "auto"}}
        [:div {:style {:padding "16px" :border-bottom (str "1px solid " t/border-default)
                       :display "flex" :justify-content "space-between" :align-items "center"}}
         [:span {:style {:font-weight (:semibold t/font-weights)}} "Notificações"]
         [:button {:style {:background "none" :border "none" :cursor "pointer"
                           :font-size (:xs t/font-sizes) :color t/text-secondary}
                   :on-click #(rf/dispatch [:notifications/read-all])}
          "Marcar todas como lidas"]]
        (if (empty? items)
          [:div {:style {:padding "32px" :text-align "center" :color t/text-disabled}}
           "Nenhuma notificação"]
          (for [n items]
            ^{:key (:id n)}
            [:div {:style {:padding "12px 16px"
                           :border-bottom (str "1px solid " t/bg-subtle)
                           :background (if (:read n) "transparent" t/beige-100)
                           :cursor "pointer"}
                   :on-click #(do (rf/dispatch [:notifications/mark-read (:id n)])
                                  (reset! open? false))}
             [:div {:style {:font-size (:sm t/font-sizes) :font-weight (if (:read n) (:regular t/font-weights) (:medium t/font-weights))}}
              (:title n)]
             [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :margin-top "4px"}}
              (:message n)]]))])]))
```

- [ ] **Step 2: Wire notification bell into header (layout.cljs)**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/ds/notifications.cljs frontend/src/app/ds/layout.cljs
git commit -m "feat: add notification bell with dropdown, unread badge, mark-as-read

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

### Task 5.3: Frontend Docker + Nginx

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

- [ ] **Step 1: Create nginx.conf**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy (K8s service discovery)
    location /api/ {
        proxy_pass http://plataforma-comissoes-backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Cache static assets
    location /js/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Health check
    location /nginx-health {
        return 200 "ok";
    }
}
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
# Build stage
FROM node:20-slim AS build
WORKDIR /app
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile
COPY . .
RUN yarn release

# Serve stage
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/resources/public /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://localhost/nginx-health || exit 1
```

- [ ] **Step 3: Create frontend Helm values**

Add frontend section to `.k8s/helm/stag/values-frontend.yaml` and `.k8s/helm/prod/values-frontend.yaml`.

- [ ] **Step 4: Update .gitlab-ci.yml with frontend stages**

Add `test-frontend`, `lint-frontend`, `build-frontend`, `push-frontend`, `deploy-frontend-stag`, `deploy-frontend-prod` stages.

- [ ] **Step 5: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf .k8s/ .gitlab-ci.yml
git commit -m "feat: add frontend Docker build with Nginx, Helm values, and CI stages

X-AI-Gen: true
X-AI-Model: claude-opus-4-6"
```

---

**Plan complete and saved to `docs/superpowers/plans/2026-03-27-plataforma-comissoes-frontend.md`.**
