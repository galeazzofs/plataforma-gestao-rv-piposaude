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

(def ^:private meses
  ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
   "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(defn- month-label [month year]
  (let [m (cond (number? month) month
                (string? month) (js/parseInt month)
                :else nil)]
    (if (and m (<= 1 m 12))
      (str (nth meses (dec m)) "/" year)
      (str "·/" (or year "·")))))

(def ^:private status-labels
  {"DRAFT"         "Rascunho"
   "CALCULATING"   "Calculando"
   "VALIDATING"    "Com EVs"
   "LIDER_REVIEW"  "Revisão líder"
   "REVOPS_REVIEW" "Revisão RevOps"
   "LOCKED"        "Fechada"})

(defn- status-label [status]
  (get status-labels status (or status "·")))

(defn- status-class [status]
  (case status
    "DRAFT"         "badge-draft"
    "CALCULATING"   "badge-calc"
    "VALIDATING"    "badge-validating"
    "LIDER_REVIEW"  "badge-review"
    "REVOPS_REVIEW" "badge-review"
    "LOCKED"        "badge-paid"
    "badge-locked"))

(defn- status->badge [status]
  [:span {:class (str "badge " (status-class status))}
   (status-label status)])

(defn- count-pill [n tone]
  [:span {:style {:background (case tone
                                :danger  "var(--danger-lightest)"
                                :warning "var(--warning-lightest)"
                                :success "var(--success-lightest)"
                                "var(--bg-2)")
                  :color (case tone
                           :danger  "var(--danger-text)"
                           :warning "var(--warning-text)"
                           :success "var(--success-text)"
                           "var(--fg-3)")
                  :font-family "var(--font-mono)" :font-size "11px"
                  :padding "1px 7px" :border-radius "var(--r-pill)"
                  :margin-left "6px"}}
   n])

(defn- tab-button [active-tab k label n tone]
  [:button {:type "button"
            :class (str "tab" (when (= @active-tab k) " active"))
            :role "tab" :aria-selected (str (= @active-tab k))
            :on-click #(reset! active-tab k)}
   label [count-pill n tone]])

(defn- match-status-label [status]
  (case status
    "MATCHED" "Matcheada"
    "UNMATCHED" "Não matcheada"
    "EXPIRED" "Fora de vigência"
    "UNSUPPORTED_PRODUCT" "Não suportado"
    "APOLICE_FINALIZADA" "Apólice finalizada"
    (or status "·")))

(defn- match-status->badge [status]
  [:span {:class (str "badge "
                      (case status
                        "MATCHED" "badge-approved"
                        "UNMATCHED" "badge-contested"
                        "EXPIRED" "badge-review"
                        "UNSUPPORTED_PRODUCT" "badge-locked"
                        "APOLICE_FINALIZADA" "badge-paid"
                        "badge-review"))}
   (match-status-label status)])

(defn period-empty?
  "True when the period has no imported NFs of any match status."
  [totals]
  (zero? (+ (or (:matched_nf_count totals) 0)
            (or (:unmatched_count totals) 0)
            (or (:expired_count totals) 0)
            (or (:nao_suportado_count totals) 0)
            (or (:apolices_finalizadas_count totals) 0))))

(defn empty-period-hint
  "Callout shown when the apuração's month has no imported NFs, pointing at the
  months that actually carry financial data (apuração is per-month now)."
  [month year periods]
  (when (seq periods)
    [:div.callout.-warning {:style {:margin-bottom "16px"}}
     [layout/icon "info" {:width 20 :height 20}]
     [:div {:style {:flex 1}}
      [:strong (str "Nenhuma NF importada para " (month-label month year))]
      [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
       "A apuração é mensal: ela só enxerga as NFs cujo recebimento caiu no "
       "mês escolhido. Os dados financeiros que você importou estão nestes "
       "meses — selecione um deles para apurar:"]
      [:div {:style {:font-family "var(--font-mono)" :font-size "12px"
                     :color "var(--fg-1)" :margin-top "6px"}}
       (str/join " · "
                 (for [p periods]
                   (str (month-label (:month p) (:year p))
                        " (" (:nf_count p) " NFs)")))]]]))

;; ── NF table for unmatched/expired/nao-suportado ──

(defn nf-table [rows]
  (let [show-finalizada-mes? (boolean (some :apolice_finalizada_mes rows))
        col-span (if show-finalizada-mes? 8 7)]
    [:table.table
   [:thead
    [:tr
     [:th "Cliente"] [:th "Operadora"] [:th "Produto"] [:th "Data"]
     [:th "Tipo receita"] [:th.right "NF Líquido"] [:th "Status"]
     (when show-finalizada-mes? [:th "Ciclo 12/12"])]]
   [:tbody
    (if (empty? rows)
      [:tr [:td {:col-span col-span :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
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
         [:td [match-status->badge (:match_status r)]]
         (when show-finalizada-mes?
           [:td.num.muted (or (:apolice_finalizada_mes r) "·")])]))]]))

(defn- export-csv-button [rows filename]
  [:button.btn.btn-secondary.btn-sm
   {:on-click
    (fn []
      (let [headers ["cliente_mae" "operadora" "produto" "data_recebimento"
                     "tipo_receita" "nf_liquido" "match_status"
                     "apolice_finalizada_mes"]
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

;; ── Policy block (one per Policy under an EV) ─────────────

(defn- policy-block []
  (let [open? (r/atom false)]
    (fn [policy]
      [:div {:style {:border "1px solid var(--border-subtle)"
                     :border-radius "var(--r-sm)"
                     :margin-bottom "8px"
                     :background "var(--bg-1)"}}
       [:button {:type "button"
                 :aria-expanded (str @open?)
                 :style {:display "flex" :justify-content "space-between" :align-items "center"
                         :padding "12px 14px" :cursor "pointer"
                         :width "100%" :background "transparent" :border 0
                         :font "inherit" :color "inherit" :text-align "left"}
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
         [:button {:type "button"
                   :aria-expanded (str @open?)
                   :style {:padding "16px 20px" :cursor "pointer"
                           :display "flex" :justify-content "space-between" :align-items "center"
                           :width "100%" :background "transparent" :border 0
                           :font "inherit" :color "inherit" :text-align "left"}
                   :on-click #(swap! open? not)}
          [:div
           [:div.name {:style {:font-size "14px"}}
            (:ev_name ev)
            (when (:ev_left_company ev)
              [:span.badge.badge-review {:style {:margin-left "8px"}}
               "Saiu"])]
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

(defn por-ev-tab []
  (let [tipo-filter (r/atom "Todos")
        op-filter   (r/atom "Todas")]
    (fn [ev-summary]
      (let [all-ops (->> ev-summary
                         (mapcat :policies)
                         (map :operadora)
                         (remove nil?)
                         distinct sort)]
        [:div
         [:div.filter-row {:role "group" :aria-label "Filtros"}
          (for [t ["Todos" "Comissão" "Fee por Vida" "Premiação" "Patrocínio - Eventos" "Agenciamento"]]
            ^{:key t}
            [:button {:type "button"
                      :class (str "chip" (when (= t @tipo-filter) " active"))
                      :aria-pressed (str (= t @tipo-filter))
                      :on-click #(reset! tipo-filter t)}
             t])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          [:button {:type "button"
                    :class (str "chip" (when (= "Todas" @op-filter) " active"))
                    :aria-pressed (str (= "Todas" @op-filter))
                    :on-click #(reset! op-filter "Todas")} "Todas"]
          (for [o all-ops]
            ^{:key o}
            [:button {:type "button"
                      :class (str "chip" (when (= o @op-filter) " active"))
                      :aria-pressed (str (= o @op-filter))
                      :on-click #(reset! op-filter o)}
             o])]
         (if (empty? ev-summary)
           [:div.card [:div {:style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                       "Nenhum EV com comissão calculada"]]
           [:div
            (for [ev ev-summary]
              ^{:key (:ev_id ev)}
              [ev-row ev @tipo-filter @op-filter])])]))))

;; ── Monthly review summary ────────────────────────────────

(defn- brief-item [{:keys [label value tone]}]
  [:div {:class (str "appraisal-brief-item"
                     (when tone (str " -" (name tone))))}
   [:span.appraisal-brief-label label]
   [:strong value]])

(defn- review-brief [appraisal totals unmatched expired finalizadas nao-sup]
  [:div.card.appraisal-review-brief
   [:div.appraisal-brief-main
    [:div.appraisal-brief-label "competência mensal"]
    [:div.appraisal-brief-title (month-label (:month appraisal) (:year appraisal))]
    [status->badge (:status appraisal)]
    [:div.card-sub "Resumo operacional antes de liberar ou fechar a Comissão EV."]]
   [:div.appraisal-brief-grid
    [brief-item {:label "NFs OK"
                 :value (str (or (:matched_nf_count totals) 0))
                 :tone :success}]
    [brief-item {:label "não matcheadas"
                 :value (str (count unmatched))
                 :tone :danger}]
    [brief-item {:label "fora de vigência"
                 :value (str (count expired))
                 :tone :warning}]
    [brief-item {:label "finalizadas / não suportado"
                 :value (str (+ (count finalizadas) (count nao-sup)))}]]])

;; ── Contestation panel (issue #36) ────────────────────────

(defn- contestation-panel [appraisal user]
  (let [contest-open? (r/atom false)
        contest-text  (r/atom "")
        resolve-text  (r/atom "")]
    (fn [appraisal user]
      (let [id        (:id appraisal)
            status    (:status appraisal)
            has?      (:has_contestation appraisal)
            note      (:contestation_note appraisal)
            res-note  (:resolution_note appraisal)
            role      (:role user)
            admin?    (= role "ADMIN")
            can-contest? (and (not has?) (= status "VALIDATING"))]
        (cond
          ;; Open contestation — show note + resolution form for admins
          has?
          [:div.callout.-danger
           [layout/icon "alert" {:width 20 :height 20}]
           [:div {:style {:flex 1}}
            [:strong "Contestação aberta"]
            [:div {:style {:font-size "13px" :color "var(--fg-2)"
                           :margin-top "4px" :white-space "pre-wrap"}}
             (or note "·")]
            (when admin?
              [:div {:style {:margin-top "12px"}}
               [:textarea
                {:value @resolve-text
                 :placeholder "Devolutiva (obrigatório) — descreva como o problema foi resolvido."
                 :on-change #(reset! resolve-text (-> % .-target .-value))
                 :rows 3
                 :style {:width "100%" :font-family "var(--font-sans)"
                         :font-size "13px" :padding "8px"
                         :border "1px solid var(--border-subtle)"
                         :border-radius "var(--r-sm)"}}]
               [:div {:style {:margin-top "8px" :display "flex" :gap "8px"}}
                [:button.btn.btn-primary.btn-sm
                 {:disabled (clojure.string/blank? @resolve-text)
                  :on-click (fn []
                              (rf/dispatch [:revops/resolve-contestation
                                            id @resolve-text])
                              (reset! resolve-text ""))}
                 "Resolver e devolver para validação"]]])]]

          ;; Resolution closed — small acknowledgement
          (and (not has?) res-note)
          [:div.callout.-success
           [layout/icon "check" {:width 20 :height 20}]
           [:div {:style {:flex 1}}
            [:strong "Contestação resolvida"]
            [:div {:style {:font-size "13px" :color "var(--fg-2)"
                           :margin-top "4px" :white-space "pre-wrap"}}
             res-note]]]

          ;; Can contest — show button + textarea (toggled)
          can-contest?
          [:div.callout.-neutral
           [layout/icon "info" {:width 20 :height 20}]
           [:div {:style {:flex 1}}
            [:strong "Contestar valor"]
            [:div {:style {:font-size "13px" :color "var(--fg-3)"
                           :margin-top "2px"}}
             "Discordou do valor calculado? Abra uma contestação — a "
             "apuração vai direto para revisão do RevOps."]
            (when @contest-open?
              [:div {:style {:margin-top "10px"}}
               [:textarea
                {:value @contest-text
                 :placeholder "Motivo da contestação (obrigatório)"
                 :on-change #(reset! contest-text (-> % .-target .-value))
                 :rows 3
                 :style {:width "100%" :font-family "var(--font-sans)"
                         :font-size "13px" :padding "8px"
                         :border "1px solid var(--border-subtle)"
                         :border-radius "var(--r-sm)"}}]
               [:div {:style {:margin-top "8px" :display "flex" :gap "8px"}}
                [:button.btn.btn-primary.btn-sm
                 {:disabled (clojure.string/blank? @contest-text)
                  :on-click (fn []
                              (rf/dispatch [:revops/contest-appraisal
                                            id @contest-text])
                              (reset! contest-open? false)
                              (reset! contest-text ""))}
                 "Confirmar contestação"]
                [:button.btn.btn-secondary.btn-sm
                 {:on-click #(do (reset! contest-open? false)
                                 (reset! contest-text ""))}
                 "Cancelar"]]])]
           (when-not @contest-open?
             [:button.btn.btn-secondary.btn-sm
              {:on-click #(reset! contest-open? true)}
              "Contestar"])]

          :else nil)))))

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
            apolices-finalizadas (or (:apolices_finalizadas appraisal) [])
            totals     (or (:totals appraisal) {})
            user       @(rf/subscribe [:auth/current-user])
            route-name @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:current-route route-name :user user
          :crumbs ["plataforma rv" "admin" "apurações" (month-label (:month appraisal) (:year appraisal))]
          :title (str "Revisão · " (month-label (:month appraisal) (:year appraisal)))
          :subtitle (if (:status appraisal)
                      (str "Competência mensal · " (status-label (:status appraisal)))
                      "Competência mensal")
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

         ;; Contestation panel (issue #36)
         [contestation-panel appraisal user]

         ;; Mês sem NFs importadas — aponta os meses que têm dados
         (when (period-empty? totals)
           [empty-period-hint (:month appraisal) (:year appraisal)
            (:financial_data_periods appraisal)])

         ;; Atingimentos faltando — apurados como 0% (não bloqueia a apuração)
         (when-let [missing (seq (:missing_achievements appraisal))]
           [:div.callout.-warning
            [layout/icon "alert" {:width 20 :height 20}]
            [:div {:style {:flex 1}}
             [:strong "Atingimentos faltando — apurados como 0%"]
             [:div {:style {:font-size "13px" :color "var(--fg-2)" :margin-top "2px"}}
              "Estes EVs estão sem atingimento usado pela regra do gongo e "
              "saíram no piso da tabela. Preencha em Atingimento EV e recalcule:"]
             [:div {:style {:font-family "var(--font-mono)" :font-size "12px"
                            :color "var(--fg-1)" :margin-top "6px"}}
              (str/join " · " missing)]]])

         [review-brief appraisal totals unmatched expired apolices-finalizadas nao-sup]

         ;; KPIs row
         [:div.kpi-grid
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "comissão total"]
           [:div.kpi-value [:span.currency "R$"]
            (or (fmt-int (:total_commission totals)) "·")]
           [:div.kpi-foot "valor da competência"]]
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs"]
           [:div.kpi-value (str (or (:ev_count totals) 0))]
           [:div.kpi-foot "com comissão"]]
          [:div.kpi
           [:div.kpi-label [layout/icon "doc" {:width 14 :height 14}] "apólices"]
           [:div.kpi-value (str (or (:policy_count totals) 0))]
           [:div.kpi-foot "na memória"]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "NFs OK"]
           [:div.kpi-value (str (or (:matched_nf_count totals) 0))]
           [:div.kpi-foot "matcheadas"]]]

         ;; Tabs card
         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "0 24px"}}
           [:div.tabs {:role "tablist" :aria-label "Visões de apuração"}
            [tab-button active-tab :por-ev "Por EV" (count ev-summary) :neutral]
            [tab-button active-tab :unmatched "Não matcheadas" (count unmatched) :danger]
            [tab-button active-tab :expired "Fora de vigência" (count expired) :warning]
            [tab-button active-tab :apolices-finalizadas "Apólices finalizadas" (count apolices-finalizadas) :success]
            [tab-button active-tab :nao-sup "Não suportado" (count nao-sup) :neutral]]]
          [:div {:style {:padding "20px 24px"}}
           (case @active-tab
             :por-ev    [por-ev-tab ev-summary]
             :unmatched [:<>
                         [:div {:style {:margin-bottom "12px"}}
                          [export-csv-button unmatched "nao-matcheadas.csv"]]
                         [nf-table unmatched]]
             :expired   [:<>
                         [:div {:style {:margin-bottom "12px"}}
                          [export-csv-button expired "fora-vigencia.csv"]]
                         [nf-table expired]]
             :apolices-finalizadas [:<>
                                     [:div {:style {:margin-bottom "12px"}}
                                      [export-csv-button apolices-finalizadas "apolices-finalizadas.csv"]]
                                     [nf-table apolices-finalizadas]]
             :nao-sup   [:<>
                         [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-bottom "12px"}}
                          "Linhas com produto não suportado pelo modelo (Mental, Fitness)."]
                         [nf-table nao-sup]])]]]))))
