(ns app.views.revops.cn-appraisal
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.views.cn.calc :as calc]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.util.url :as url]
            [app.auth.subs]))

;; Apuração mensal do CN. A grade espelha o simulador (meta de vidas
;; automática pelo porte + prévia ao vivo de score/mult/comissão), mas aqui
;; o realizado é digitado por CN e "Rodar apuração" persiste de verdade.

(rf/reg-event-fx
 :revops/fetch-cn-appraisals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-appraisals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-appraisal "?month=" month "&year=" year)
           :on-success [:revops/cn-appraisals-loaded]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-db
 :revops/cn-appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-appraisals] (:data response))
       (assoc-in [:admin :cn-appraisals-loading?] false))))

(rf/reg-event-db
 :revops/cn-appraisals-error
 (fn [db _] (assoc-in db [:admin :cn-appraisals-loading?] false)))

;; Goals carry, per active CN, the SAO target + porte that drive the auto
;; lives target — exactly the inputs the entry grid needs before a run.
(rf/reg-event-fx
 :revops/fetch-cn-appraisal-goals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-appraisal-goals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-goals "?month=" month "&year=" year)
           :on-success [:revops/cn-appraisal-goals-loaded]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-db
 :revops/cn-appraisal-goals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-appraisal-goals] (:data response))
       (assoc-in [:admin :cn-appraisal-goals-loading?] false))))

(rf/reg-event-fx
 :revops/run-cn-appraisal
 (fn [{:keys [db]} [_ payload]]
   {:db   (update-in db [:admin] dissoc :cn-appraisal-run-error)
    :http {:method     :post
           :url        ep/cn-appraisal
           :body       payload
           :on-success [:revops/cn-appraisal-done (:month payload) (:year payload)]
           :on-failure [:revops/cn-appraisal-run-error]}}))

(rf/reg-event-fx
 :revops/cn-appraisal-done
 (fn [{:keys [db]} [_ month year _response]]
   {:db       (update-in db [:admin] dissoc :cn-appraisal-run-error)
    :dispatch [:revops/fetch-cn-appraisals month year]}))

(rf/reg-event-db
 :revops/cn-appraisal-run-error
 (fn [db [_ response]]
   (assoc-in db [:admin :cn-appraisal-run-error] (:error response))))

(rf/reg-event-fx
 :revops/finalize-cn-appraisal
 (fn [_ [_ id month year]]
   {:http {:method     :post
           :url        (ep/cn-appraisal-finalize id)
           :body       {}
           :on-success [:revops/fetch-cn-appraisals month year]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-fx
 :revops/transition-cn-appraisal
 (fn [_ [_ id to-status month year]]
   {:http {:method     :post
           :url        (str ep/cn-appraisal "/" id "/transition")
           :body       {:to to-status}
           :on-success [:revops/fetch-cn-appraisals month year]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-fx
 :revops/contest-cn-appraisal
 (fn [_ [_ id note month year]]
   {:http {:method     :post
           :url        (str ep/cn-appraisal "/" id "/contest")
           :body       {:note note}
           :on-success [:revops/fetch-cn-appraisals month year]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-fx
 :revops/resolve-cn-contestation
 (fn [_ [_ id resolution-note month year]]
   {:http {:method     :post
           :url        (str ep/cn-appraisal "/" id "/resolve-contestation")
           :body       {:resolution_note resolution-note}
           :on-success [:revops/fetch-cn-appraisals month year]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-sub :revops/cn-appraisals (fn [db _] (get-in db [:admin :cn-appraisals] [])))
(rf/reg-sub :revops/cn-appraisals-loading? (fn [db _] (get-in db [:admin :cn-appraisals-loading?])))
(rf/reg-sub :revops/cn-appraisal-goals (fn [db _] (get-in db [:admin :cn-appraisal-goals] [])))
(rf/reg-sub :revops/cn-appraisal-run-error (fn [db _] (get-in db [:admin :cn-appraisal-run-error])))

(defn- fmt-int [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (.toLocaleString (js/Math.round n) "pt-BR")))))

(defn- pct [v]
  (when (some? v) (-> v (* 100) (.toFixed 0))))

(defn- mult [v]
  (when (some? v) (-> v (.toFixed 2) (str/replace "." ","))))

(def ^:private cn-stepper-states
  ["DRAFT" "CALCULATING" "VALIDATING" "LIDER_REVIEW" "REVOPS_REVIEW" "LOCKED"])

(def ^:private cn-stepper-labels
  {"DRAFT"         "Draft"
   "CALCULATING"   "Calculating"
   "VALIDATING"    "Validating"
   "LIDER_REVIEW"  "Líder Review"
   "REVOPS_REVIEW" "RevOps Review"
   "LOCKED"        "Locked"})

;; A CN counts as having validated own once their row moved past VALIDATING.
(def ^:private validated-statuses
  #{"LIDER_REVIEW" "REVOPS_REVIEW" "LOCKED"})

(defn- status->badge [status]
  (case status
    "DRAFT"         [:span.badge.badge-draft "Draft"]
    "CALCULATING"   [:span.badge.badge-calc "Calculating"]
    "VALIDATING"    [:span.badge.badge-validating "Validating"]
    "LIDER_REVIEW"  [:span.badge.badge-review "Líder Review"]
    "REVOPS_REVIEW" [:span.badge.badge-review "RevOps Review"]
    "LOCKED"        [:span.badge.badge-paid "Locked"]
    [:span.badge.badge-locked (or status "·")]))

(defn- cn-stepper [current]
  (let [idx (max 0 (.indexOf (clj->js cn-stepper-states) (or current "DRAFT")))]
    [:div.stepper
     (for [[i s] (map-indexed vector cn-stepper-states)
           :let [done?    (< i idx)
                 current? (= i idx)]]
       ^{:key s}
       [:<>
        [:div.stepper-stack
         [:div {:class (str "step" (cond done? " done" current? " current"))}
          [:div.step-dot (str (inc i))]]
         [:div.step-label (cn-stepper-labels s)]]
        (when (< i (dec (count cn-stepper-states)))
          [:div.step-line])])]))

(defn- next-status-action
  "Return [label, target-status] for the next admin action on this status,
   or nil when there's nothing to do (LOCKED)."
  [status]
  (case status
    "DRAFT"          ["Iniciar"        "CALCULATING"]
    "CALCULATING"    ["Liberar p/ EV"  "VALIDATING"]
    "VALIDATING"     ["Avançar"        "LIDER_REVIEW"]
    "LIDER_REVIEW"   ["Aprovar (Líder)" "REVOPS_REVIEW"]
    "REVOPS_REVIEW"  ["Fechar"         "LOCKED"]
    nil))

(defn- contest-modal
  "In-page modal replacing js/prompt for both contesting and resolving.
   Mode is :contest or :resolve. Submits when note is non-empty."
  [{:keys [state on-submit]}]
  (let [{:keys [open? mode row]} @state
        contest? (= mode :contest)
        title    (if contest? "Contestar apuração" "Resolver contestação")
        label    (if contest? "Motivo da contestação" "Devolutiva ao CN")
        cta      (if contest? "Enviar contestação" "Enviar devolutiva")
        note-key :note]
    [modal/modal
     {:open? open?
      :title title
      :size  :sm
      :on-close #(swap! state assoc :open? false :note "")}
     (when contest?
       [:p {:style {:color "var(--fg-3)" :font-size "13px"
                    :margin "0 0 14px" :line-height "1.55"}}
        "A apuração será movida diretamente para RevOps Review com a contestação aberta."])
     (when (not contest?)
       [:p {:style {:color "var(--fg-3)" :font-size "13px"
                    :margin "0 0 14px" :line-height "1.55"}}
        (str "Contestação atual: "
             (or (:contestation_note row) "—"))])
     [:label {:style {:display "block" :font-size "12px"
                      :color "var(--fg-2)" :margin-bottom "6px"
                      :font-family "var(--font-mono)"
                      :text-transform "uppercase"
                      :letter-spacing "0.04em"}}
      label " *"]
     [:textarea
      {:auto-focus true
       :rows 4
       :value (or (note-key @state) "")
       :on-change #(swap! state assoc note-key (-> % .-target .-value))
       :style {:width "100%"
               :padding "10px 12px"
               :border "1px solid var(--border-default)"
               :border-radius "6px"
               :font-family "inherit" :font-size "13px"
               :resize "vertical"
               :background "var(--bg-main)"
               :color "var(--fg-1)"}}]
     [:div {:style {:display "flex" :gap "8px"
                    :justify-content "flex-end" :margin-top "16px"}}
      [:button.btn.btn-secondary
       {:type "button"
        :on-click #(swap! state assoc :open? false :note "")}
       "Cancelar"]
      [:button.btn.btn-primary
       {:type "button"
        :disabled (-> (note-key @state) (or "") str/trim seq nil? boolean)
        :on-click (fn []
                    (let [note (-> (note-key @state) (or "") str/trim)]
                      (when (seq note)
                        (on-submit {:mode mode :id (:id row) :note note})
                        (swap! state assoc :open? false :note ""))))}
       cta]]]))

(defn- realizado-input [{:keys [value disabled width on-change]}]
  [:input.field-input
   {:type "number" :inputMode "decimal" :min "0"
    :style {:width (or width "118px") :text-align "right" :padding "6px 10px"}
    :placeholder "0"
    :disabled disabled
    :value value
    :on-change #(on-change (.. % -target -value))}])

(defn page []
  (let [filter-s    (r/atom {:month (or (url/query-param "month") "4")
                             :year  (or (url/query-param "year") "2026")})
        edits       (r/atom {})
        modal-state (r/atom {:open? false :mode nil :row nil :note ""})
        fetch-period!
        (fn [m y]
          (rf/dispatch [:revops/fetch-cn-appraisal-goals m y])
          (rf/dispatch [:revops/fetch-cn-appraisals m y]))]
    (fetch-period! (:month @filter-s) (:year @filter-s))
    (rf/dispatch [:revops/fetch-settings])
    (fn []
      (let [appraisals @(rf/subscribe [:revops/cn-appraisals])
            goals      @(rf/subscribe [:revops/cn-appraisal-goals])
            loading?   @(rf/subscribe [:revops/cn-appraisals-loading?])
            run-error  @(rf/subscribe [:revops/cn-appraisal-run-error])
            settings   @(rf/subscribe [:revops/settings])
            user       @(rf/subscribe [:auth/current-user])
            route      @(rf/subscribe [:current-route-name])
            ramp-bonus (:cn_rampagem_bonus_sao settings)
            m (:month @filter-s)
            y (:year @filter-s)
            appraisal-by-cn (into {} (map (juxt :cn_id identity)) (or appraisals []))
            field-val (fn [cn-id k fallback]
                        (let [edited (get-in @edits [cn-id k] ::none)]
                          (if (= edited ::none) (or fallback "") edited)))
            rows (mapv (fn [g]
                         (let [a (get appraisal-by-cn (:cn_id g))
                               vidas-meta (calc/vidas-meta-from-sao
                                           (calc/->num (:sao_target g)) (:porte g))
                               sao-real (field-val (:cn_id g) :sao_realizado
                                                   (when a (:sao_realizado a)))
                               vidas-real (field-val (:cn_id g) :vidas_realizado
                                                     (when a (:vidas_realizado a)))
                               neg-real (field-val (:cn_id g) :negocios_cadencia_realizado
                                                   (when a (:negocios_cadencia_realizado a)))
                               emails-real (field-val (:cn_id g) :emails_realizado
                                                      (when a (:emails_realizado a)))
                               qualis-real (field-val (:cn_id g) :qualis_agendadas_realizado
                                                      (when a (:qualis_agendadas_realizado a)))
                               sao-fora (field-val (:cn_id g) :sao_fora_da_meta
                                                   (when a (:sao_fora_da_meta a)))
                               preview (calc/calculate-auto
                                        {:nivel (:nivel g)
                                         :em_rampagem (:em_rampagem g)
                                         :sao_meta (:sao_target g)
                                         :sao_realizado sao-real
                                         :sao_real sao-real
                                         :vidas_meta vidas-meta
                                         :vidas_realizado vidas-real
                                         :neg_meta (:negocios_cadencia_meta g)
                                         :neg_real neg-real
                                         :emails_meta (:emails_meta g)
                                         :emails_real emails-real
                                         :qualis_meta (:qualis_agendadas_meta g)
                                         :qualis_real qualis-real
                                         :sao_fora_da_meta sao-fora
                                         :bonus_sao ramp-bonus})]
                           (assoc g
                                  :appraisal a
                                  :vidas_meta vidas-meta
                                  :sao_realizado sao-real
                                  :vidas_realizado vidas-real
                                  :negocios_cadencia_realizado neg-real
                                  :emails_realizado emails-real
                                  :qualis_agendadas_realizado qualis-real
                                  :sao_fora_da_meta sao-fora
                                  :preview preview)))
                       (or goals []))
            total-rows (count rows)
            total      (reduce + 0 (map #(get-in % [:preview :commission_amount] 0) rows))
            validated  (count (filter #(validated-statuses (get-in % [:appraisal :status])) rows))
            validated-pct (if (pos? total-rows)
                            (-> (/ validated total-rows) (* 100) js/Math.round)
                            0)
            missing-goal? (some #(nil? (:sao_target %)) rows)
            ready?     (and (seq rows) (not missing-goal?))
            dominant   (let [statuses (->> rows (keep #(get-in % [:appraisal :status])))]
                         (when (seq statuses)
                           (->> statuses frequencies (sort-by val >) first first)))
            run!       (fn []
                         (let [s0 (fn [x] (let [s (str (or x ""))] (if (str/blank? s) "0" s)))
                               inputs (mapv (fn [row]
                                              {:cn_id (:cn_id row)
                                               :sao_realizado (s0 (:sao_realizado row))
                                               :vidas_realizado (s0 (:vidas_realizado row))
                                               :negocios_cadencia_realizado (s0 (:negocios_cadencia_realizado row))
                                               :emails_realizado (s0 (:emails_realizado row))
                                               :qualis_agendadas_realizado (s0 (:qualis_agendadas_realizado row))
                                               :sao_fora_da_meta (s0 (:sao_fora_da_meta row))})
                                            rows)]
                           (rf/dispatch [:revops/run-cn-appraisal
                                         {:month m :year y :inputs inputs}])
                           (reset! edits {})))
            on-modal-submit
            (fn [{:keys [mode id note]}]
              (case mode
                :contest (rf/dispatch [:revops/contest-cn-appraisal id note m y])
                :resolve (rf/dispatch [:revops/resolve-cn-contestation id note m y])
                nil))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "vendas" "apuração CN"]
          :title "Apuração Mensal · CN"
          :subtitle (str total-rows " consultores · " m "/" y)
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(fetch-period! m y)}
            [layout/icon "refresh" {:width 14 :height 14}] "Buscar"]
           [:button.btn.btn-primary
            {:disabled (not ready?)
             :title (when-not ready?
                      "Defina a meta SAO de todos os CNs em Metas CN antes de apurar")
             :on-click run!}
            [layout/icon "target" {:width 14 :height 14}] "Rodar apuração"]]}

         [contest-modal {:state modal-state :on-submit on-modal-submit}]

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [mm (range 1 13)]
            ^{:key mm}
            [:button {:type "button"
                      :class (str "chip" (when (= (str mm) m) " active"))
                      :aria-pressed (str (= (str mm) m))
                      :aria-label (str "Mês " mm)
                      :on-click #(do (swap! filter-s assoc :month (str mm))
                                     (reset! edits {})
                                     (fetch-period! (str mm) y))}
             (str mm)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [yy ["2025" "2026"]]
            ^{:key yy}
            [:button {:type "button"
                      :class (str "chip" (when (= yy y) " active"))
                      :aria-pressed (str (= yy y))
                      :on-click #(do (swap! filter-s assoc :year yy)
                                     (reset! edits {})
                                     (fetch-period! m yy))}
             yy])]

         (when run-error
           [:div.callout.sim-error
            [layout/icon "alert" {:width 20 :height 20}]
            [:div {:style {:flex 1}}
             [:strong "Não foi possível apurar"]
             [:p {:style {:font-size "13px" :margin-top "2px"}}
              (if (= (:code run-error) "MISSING_GOALS")
                (str "Faltam metas para: "
                     (str/join ", " (or (:missing run-error) [])))
                (or (:message run-error) "Erro ao rodar a apuração."))]]])

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "consultores"]
           [:div.kpi-value (str total-rows)]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "comissão prévia"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "·")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}]
            "% time validou"]
           [:div.kpi-value
            (str validated "/" total-rows)
            [:span {:style {:font-size "13px" :color "var(--fg-3)"
                            :margin-left "8px" :font-family "var(--font-mono)"}}
             (str "(" validated-pct "%)")]]]]

         (when (seq dominant)
           [:div.card {:style {:padding "18px 20px"}}
            [:h3 "Progresso geral"]
            [cn-stepper dominant]
            [:div {:style {:margin-top "10px" :font-size "12px"
                           :color "var(--fg-3)"}}
             (str validated " de " total-rows " CNs validaram own ("
                  validated-pct "%) · o Líder pode revisar quando atingir 100%.")]])

         [:div.callout
          [layout/icon "info" {:width 20 :height 20}]
          [:div {:style {:flex 1}}
           [:strong "Como funciona"]
           [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
            "Digite o SAO e as vidas realizados de cada CN. A meta de vidas é "
            "calculada sozinha pelo porte (SAO × fator) e a prévia de comissão "
            "atualiza ao vivo, como no simulador. Clique em Rodar apuração para salvar."]]]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "CN"]
             [:th.right "Meta SAO"]
             [:th.right "SAO realiz."]
             [:th.right "Meta vidas"]
             [:th.right "Vidas realiz."]
             [:th.center "Score"]
             [:th.right "Mult."]
             [:th.right "Comissão"]
             [:th "Status"]
             [:th.right "Ação"]]]
           [:tbody
            (cond
              (and loading? (empty? rows))
              [:tr [:td {:col-span 10 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? rows)
              [:tr [:td {:col-span 10 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhum CN ativo encontrado"]]

              :else
              (for [row rows]
                ^{:key (:cn_id row)}
                (let [a           (:appraisal row)
                      cn-id       (:cn_id row)
                      has-goal?   (some? (:sao_target row))
                      locked?     (boolean (and a (:is_final a)))
                      preview     (:preview row)
                      next-action (next-status-action (:status a))
                      validating? (= (:status a) "VALIDATING")
                      contested?  (:has_contestation a)
                      ramp?       (:em_rampagem row)
                      ramp-mode   (when ramp?
                                    (let [s (calc/->num (:sao_target row))]
                                      (if (and s (pos? s)) :com-sao :sem-sao)))]
                  [:tr
                   [:td.name
                    (:cn_name row)
                    (when-not has-goal?
                      [:div [:span.badge.badge-review
                             {:style {:font-size "10px" :margin-top "4px"}}
                             "sem meta — defina em Metas CN"]])
                    (when contested?
                      [:div [:span.badge.badge-review
                             {:style {:font-size "10px" :margin-top "4px"}}
                             "⚠ contestação aberta"]])]
                   [:td.right.num (or (fmt-int (:sao_target row)) "·")]
                   [:td.right
                    (cond
                      (= ramp-mode :sem-sao)
                      [:div {:style {:display "flex" :flex-direction "column" :gap "4px" :align-items "flex-end"}}
                       [:span.muted {:style {:font-size "10px"}} "negócios / emails"]
                       [realizado-input {:value (:negocios_cadencia_realizado row)
                                         :disabled (or locked? (not has-goal?))
                                         :on-change #(swap! edits assoc-in [cn-id :negocios_cadencia_realizado] %)}]
                       [realizado-input {:value (:emails_realizado row)
                                         :disabled (or locked? (not has-goal?))
                                         :on-change #(swap! edits assoc-in [cn-id :emails_realizado] %)}]]
                      (= ramp-mode :com-sao)
                      [:div {:style {:display "flex" :flex-direction "column" :gap "4px" :align-items "flex-end"}}
                       [:span.muted {:style {:font-size "10px"}} "SAO"]
                       [realizado-input {:value (:sao_realizado row)
                                         :disabled (or locked? (not has-goal?))
                                         :on-change #(swap! edits assoc-in [cn-id :sao_realizado] %)}]]
                      :else
                      [realizado-input {:value (:sao_realizado row)
                                        :disabled (or locked? (not has-goal?))
                                        :on-change #(swap! edits assoc-in [cn-id :sao_realizado] %)}])]
                   [:td.right.num (or (fmt-int (:vidas_meta row)) "·")]
                   [:td.right
                    (cond
                      (= ramp-mode :sem-sao)
                      [:div {:style {:display "flex" :flex-direction "column" :gap "4px" :align-items "flex-end"}}
                       [:span.muted {:style {:font-size "10px"}} "SAO fora da meta"]
                       [realizado-input {:value (:sao_fora_da_meta row)
                                         :disabled (or locked? (not has-goal?))
                                         :on-change #(swap! edits assoc-in [cn-id :sao_fora_da_meta] %)}]]
                      (= ramp-mode :com-sao)
                      [:div {:style {:display "flex" :flex-direction "column" :gap "4px" :align-items "flex-end"}}
                       [:span.muted {:style {:font-size "10px"}} "qualis"]
                       [realizado-input {:value (:qualis_agendadas_realizado row)
                                         :disabled (or locked? (not has-goal?))
                                         :on-change #(swap! edits assoc-in [cn-id :qualis_agendadas_realizado] %)}]]
                      :else
                      [realizado-input {:value (:vidas_realizado row)
                                        :disabled (or locked? (not has-goal?))
                                        :on-change #(swap! edits assoc-in [cn-id :vidas_realizado] %)}])]
                   [:td.center.num (str (or (pct (:score_final preview)) "·") "%")]
                   [:td.right.num (str (or (mult (:multiplicador preview)) "·") "x")]
                   [:td.right.strong-num
                    (str "R$ " (or (fmt-int (:commission_amount preview)) "·"))]
                   [:td (if a (status->badge (:status a))
                            [:span.badge.badge-draft "a apurar"])]
                   [:td.right
                    (cond
                      locked?
                      [:span.muted {:style {:font-family "var(--font-mono)"
                                            :font-size "11px"}}
                       "fechado"]

                      (nil? a) nil

                      contested?
                      [:button.btn.btn-secondary.btn-sm
                       {:on-click #(reset! modal-state
                                          {:open? true :mode :resolve
                                           :row a :note ""})}
                       "Resolver contestação"]

                      validating?
                      [:div {:style {:display "flex" :gap "6px"
                                     :justify-content "flex-end"}}
                       [:button.btn.btn-secondary.btn-sm
                        {:on-click #(reset! modal-state
                                           {:open? true :mode :contest
                                            :row a :note ""})}
                        "Contestar"]
                       (when next-action
                         [:button.btn.btn-primary.btn-sm
                          {:on-click #(rf/dispatch
                                       [:revops/transition-cn-appraisal
                                        (:id a) (second next-action) m y])}
                          (first next-action)])]

                      next-action
                      [:button.btn.btn-primary.btn-sm
                       {:on-click #(rf/dispatch
                                    [:revops/transition-cn-appraisal
                                     (:id a) (second next-action) m y])}
                       (first next-action)]

                      :else nil)]])))]]]]))))
