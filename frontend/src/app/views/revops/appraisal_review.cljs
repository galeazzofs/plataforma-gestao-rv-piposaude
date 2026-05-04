(ns app.views.revops.appraisal-review
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Apuração · Revisão (deep view) — KPIs row + tabs (Por EV / NFs órfãs).

(defn- fmt-int [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (.toLocaleString (js/Math.round n) "pt-BR")))))

(defn- fmt-money [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (.toLocaleString n "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2})))))

(defn- fmt-pct [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (.toFixed n 1)))))

;; ── NF table for unmatched/expired/nao-suportado ──

(defn- nf-table [rows]
  [:table.table
   [:thead
    [:tr
     [:th "Cliente"] [:th "Operadora"] [:th "Produto"] [:th "Data"]
     [:th "Tipo receita"] [:th.right "NF Líquido"] [:th "Status"]]]
   [:tbody
    (if (empty? rows)
      [:tr [:td {:col-span 7 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
            "Nenhuma linha"]]
      (for [r rows]
        ^{:key (or (:id r) (hash r))}
        [:tr
         [:td (:cliente_mae r)]
         [:td.muted (:operadora r)]
         [:td.muted (:produto r)]
         [:td.num.muted (:data_recebimento r)]
         [:td (:tipo_receita r)]
         [:td.right.strong-num (str "R$ " (or (fmt-money (:nf_liquido r)) "·"))]
         [:td [:span.badge.badge-review (or (:match_status r) "·")]]]))]])

(defn- export-csv-button [rows filename]
  [:button.btn.btn-secondary.btn-sm
   {:on-click
    (fn []
      (let [headers ["cliente_mae" "operadora" "produto" "data_recebimento"
                     "tipo_receita" "nf_liquido" "match_status"]
            quote (fn [v] (str "\"" (or v "") "\""))
            line (fn [r] (str/join "," (map #(quote (get r (keyword %))) headers)))
            csv (str/join "\n" (cons (str/join "," headers) (map line rows)))
            blob (js/Blob. #js [csv] #js {:type "text/csv"})
            url (.createObjectURL js/URL blob)
            a (.createElement js/document "a")]
        (set! (.-href a) url)
        (set! (.-download a) filename)
        (.click a)
        (.revokeObjectURL js/URL url)))}
   [layout/icon "download" {:width 12 :height 12}] " Exportar CSV"])

;; ── Diagnostics: consolidated subsections ────────────────

(defn- diag-count-tone
  "Resolve background+color tokens for a diagnostics count badge."
  [tone]
  (case tone
    :danger  ["var(--danger-lightest)"  "var(--danger-dark)"]
    :warning ["var(--warning-lightest)" "var(--warning-text)"]
    ["var(--bg-2)" "var(--fg-3)"]))

(defn- diagnostics-subsection
  "Single diagnostic category inside the consolidated Diagnósticos tab.
   Header: h3 title + tonal count badge, with optional CSV export on the right.
   Body: optional explainer + nf-table.

   Visually quieter than top-level tabs, so users scan 'Por EV' first and
   only descend into diagnostics when investigating."
  [{:keys [title rows count-tone explainer csv-filename]}]
  (let [[bg fg] (diag-count-tone count-tone)]
    [:section {:style {:margin-bottom "32px"}}
     [:div {:style {:display "flex" :justify-content "space-between"
                    :align-items "baseline" :gap "16px"
                    :margin-bottom "12px" :padding-bottom "8px"
                    :border-bottom "1px solid var(--border-subtle)"}}
      [:div {:style {:display "flex" :align-items "baseline" :gap "10px"}}
       [:h3 {:style {:font-family "var(--font-heading)" :font-size "14px"
                     :font-weight 600 :color "var(--fg-1)" :margin 0
                     :letter-spacing "-0.005em"}}
        title]
       [:span {:style {:background bg :color fg
                       :font-family "var(--font-mono)" :font-size "11px"
                       :padding "1px 7px" :border-radius "var(--r-pill)"}}
        (count rows)]]
      (when csv-filename [export-csv-button rows csv-filename])]
     (when explainer
       [:p {:style {:font-size "13px" :color "var(--fg-3)"
                    :margin "0 0 12px 0" :line-height "1.5"}}
        explainer])
     [nf-table rows]]))

(defn- diagnostics-section
  "Consolidated diagnostics: three categories stacked as subsections.
   Replaces the previous three top-level tabs (Não matcheadas / Fora de
   vigência / Não suportado), which fragmented the page above the fold."
  [unmatched expired nao-sup]
  [:div
   [diagnostics-subsection
    {:title        "Não matcheadas"
     :rows         unmatched
     :count-tone   :danger
     :csv-filename "nao-matcheadas.csv"}]
   [diagnostics-subsection
    {:title        "Fora de vigência"
     :rows         expired
     :count-tone   :warning
     :csv-filename "fora-vigencia.csv"}]
   [diagnostics-subsection
    {:title      "Não suportado"
     :rows       nao-sup
     :count-tone :neutral
     :explainer  "Linhas com produto não suportado pelo modelo (Mental, Fitness)."}]])

;; ── Policy block (one per Policy under an EV) ─────────────

(defn- policy-block []
  (let [open? (r/atom false)]
    (fn [policy]
      [:div {:style {:border "1px solid var(--border-subtle)"
                     :border-radius "var(--r-sm)"
                     :margin-bottom "8px"
                     :background "var(--bg-1)"}}
       [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"
                      :padding "12px 14px" :cursor "pointer"}
              :on-click #(swap! open? not)}
        [:div
         [:strong (or (:client_name policy) "·")]
         [:span.muted {:style {:margin-left "8px" :font-size "12px"}}
          (str (or (:operadora policy) "·") " · "
               (or (:produto policy) "·") " · "
               (or (:segment policy) "·"))]]
        [:div.strong-num (str "R$ " (or (fmt-money (:subtotal policy)) "·"))]]
       (when @open?
         [:div {:style {:padding "0 14px 14px" :border-top "1px solid var(--border-subtle)"}}
          [:div {:style {:display "flex" :gap "16px" :flex-wrap "wrap"
                         :padding "10px 0" :font-size "12px" :color "var(--fg-3)"
                         :font-family "var(--font-mono)"}}
           [:div "Início vigência: " (or (:first_payment_real policy) "·")]
           [:div "Gongo: " (or (:closed_date policy) "·")]
           [:div "Atingimento: " (str (or (fmt-pct (:achievement_used_pct policy)) "·") "%")]
           [:div "% Comissão: " (str (or (fmt-pct (* 100 (or (:commission_pct policy) 0))) "·") "%")]]
          [:table.table
           [:thead [:tr [:th "Data"] [:th "Tipo"] [:th.right "NF Líquido"]]]
           [:tbody
            (if (empty? (:nfs policy))
              [:tr [:td {:col-span 3 :style {:padding "16px" :text-align "center" :color "var(--fg-3)"}}
                    "·"]]
              (for [nf (:nfs policy)]
                ^{:key (or (:id nf) (hash nf))}
                [:tr
                 [:td.num.muted (:data_recebimento nf)]
                 [:td (:tipo_receita nf)]
                 [:td.right.strong-num (str "R$ " (or (fmt-money (:nf_liquido nf)) "·"))]]))]]])])))

;; ── EV row ────────────────────────────────────────────────

(defn- ev-row []
  (let [open? (r/atom false)]
    (fn [ev tipo-filter operadora-filter]
      (let [filter-nfs (fn [nfs]
                         (if (or (nil? tipo-filter) (= "Todos" tipo-filter))
                           nfs
                           (filter #(= (:tipo_receita %) tipo-filter) nfs)))
            filtered (->> (:policies ev)
                          (filter (fn [p]
                                    (or (nil? operadora-filter)
                                        (= "Todas" operadora-filter)
                                        (= (:operadora p) operadora-filter))))
                          (map (fn [p] (update p :nfs filter-nfs))))]
        [:div.card {:style {:padding 0 :margin-bottom "12px"}}
         [:div {:style {:padding "16px 20px" :cursor "pointer"
                        :display "flex" :justify-content "space-between" :align-items "center"}
                :on-click #(swap! open? not)}
          [:div
           [:div.name {:style {:font-size "14px"}} (:ev_name ev)]
           [:div.muted {:style {:font-size "12px" :margin-top "4px"}}
            (str (:policies_count ev) " apólices · "
                 (:nf_count ev) " NFs · atingimento "
                 (or (fmt-pct (:achievement_pct ev)) "·") "%")]]
          [:div.strong-num {:style {:font-size "18px"}}
           (str "R$ " (or (fmt-money (:total_commission ev)) "·"))]]
         (when @open?
           [:div {:style {:padding "0 20px 16px"}}
            (for [p filtered]
              ^{:key (:policy_id p)} [policy-block p])])]))))

;; ── Por EV tab ────────────────────────────────────────────

(defn- por-ev-tab []
  (let [tipo-filter (r/atom "Todos")
        op-filter   (r/atom "Todas")]
    (fn [ev-summary]
      (let [all-ops (->> ev-summary
                         (mapcat :policies)
                         (map :operadora)
                         (remove nil?)
                         distinct sort)]
        [:div
         [:div.filter-row
          (for [t ["Todos" "Comissão" "Fee por Vida" "Premiação" "Patrocínio - Eventos" "Agenciamento"]]
            ^{:key t}
            [:div {:class (str "chip" (when (= t @tipo-filter) " active"))
                   :on-click #(reset! tipo-filter t)}
             t])
          [:div {:style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          [:div {:class (str "chip" (when (= "Todas" @op-filter) " active"))
                 :on-click #(reset! op-filter "Todas")} "Todas"]
          (for [o all-ops]
            ^{:key o}
            [:div {:class (str "chip" (when (= o @op-filter) " active"))
                   :on-click #(reset! op-filter o)}
             o])]
         (if (empty? ev-summary)
           [:div.card [:div {:style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                       "Nenhum EV com comissão calculada"]]
           [:div
            (for [ev ev-summary]
              ^{:key (:ev_id ev)}
              [ev-row ev @tipo-filter @op-filter])])]))))

;; ── Page ──────────────────────────────────────────────────

(defn appraisal-review-page []
  (let [route @(rf/subscribe [:current-route])
        appraisal-id (get-in route [:path-params :id])
        active-tab (r/atom :por-ev)]
    (when appraisal-id
      (rf/dispatch [:revops/fetch-appraisal-detail appraisal-id])
      (rf/dispatch [:revops/fetch-appraisals]))
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            appraisal (first (filter #(= (str (:id %)) (str appraisal-id))
                                     (or appraisals [])))
            ev-summary (or (:ev_summary appraisal) [])
            unmatched  (or (:unmatched appraisal) [])
            expired    (or (:expired appraisal) [])
            nao-sup    (or (:nao_suportado appraisal) [])
            totals     (or (:totals appraisal) {})
            user       @(rf/subscribe [:auth/current-user])
            route-name @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:current-route route-name :user user
          :crumbs ["plataforma rv" "admin" "apurações" (str "Q" (or (:quarter appraisal) "·") "/" (or (:year appraisal) "·"))]
          :title (str "Apuração · Q" (or (:quarter appraisal) "·") "/" (or (:year appraisal) "·"))
          :subtitle "Revisão da memória de cálculo · ajustes antes da validação"
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:navigate :revops/appraisal])}
            "← Voltar"]
           [:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/recalculate-appraisal appraisal-id])}
            [layout/icon "refresh" {:width 14 :height 14}] "Recalcular"]
           [:button.btn.btn-primary
            {:on-click #(rf/dispatch [:revops/release-to-validation appraisal-id])}
            [layout/icon "check" {:width 14 :height 14}] "Liberar para EVs"]]}

         ;; KPIs row
         [:div.kpi-grid
          [:div.kpi
           [:div.kpi-label "comissão total"]
           [:div.kpi-value [:span.currency "R$"]
            (or (fmt-int (:total_commission totals)) "·")]]
          [:div.kpi
           [:div.kpi-label "EVs"]
           [:div.kpi-value (str (or (:ev_count totals) 0))]]
          [:div.kpi
           [:div.kpi-label "apólices"]
           [:div.kpi-value (str (or (:policy_count totals) 0))]]
          [:div.kpi
           [:div.kpi-label "NFs OK"]
           [:div.kpi-value (str (or (:matched_nf_count totals) 0))]]]

         ;; Tabs card. Two tabs: Por EV (primary work) and Diagnósticos
         ;; (consolidated unmatched/expired/nao-suportado, scrollable).
         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "0 24px"}}
           [:div.tabs
            [:div {:class (str "tab" (when (= @active-tab :por-ev) " active"))
                   :on-click #(reset! active-tab :por-ev)}
             "Por EV "
             [:span {:style {:background "var(--bg-2)" :color "var(--fg-3)"
                             :font-family "var(--font-mono)" :font-size "11px"
                             :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
              (count ev-summary)]]
            (let [diag-total (+ (count unmatched) (count expired) (count nao-sup))
                  has-issues? (pos? diag-total)]
              [:div {:class (str "tab" (when (= @active-tab :diagnostics) " active"))
                     :on-click #(reset! active-tab :diagnostics)}
               "Diagnósticos "
               [:span {:style {:background (if has-issues? "var(--warning-lightest)" "var(--bg-2)")
                               :color (if has-issues? "var(--warning-text)" "var(--fg-3)")
                               :font-family "var(--font-mono)" :font-size "11px"
                               :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
                diag-total]])]]
          [:div {:style {:padding "20px 24px"}}
           (case @active-tab
             :por-ev      [por-ev-tab ev-summary]
             :diagnostics [diagnostics-section unmatched expired nao-sup]
             ;; Fallback for any legacy active-tab state.
             [por-ev-tab ev-summary])]]]))))
