(ns app.views.revops.cn-appraisal
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.auth.subs]))

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

(rf/reg-event-fx
 :revops/run-cn-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/cn-appraisal
           :body       payload
           :on-success [:revops/cn-appraisal-done (:month payload) (:year payload)]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-fx
 :revops/cn-appraisal-done
 (fn [_ [_ month year _response]]
   {:dispatch [:revops/fetch-cn-appraisals month year]}))

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

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct [v]
  (when v (-> v js/parseFloat (* 100) (.toFixed 0))))

(defn- mult [v]
  (when v (-> v js/parseFloat (.toFixed 2)
              (str/replace "." ","))))

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

(defn page []
  (let [filter-s    (r/atom {:month "4" :year "2026"})
        form-inputs (r/atom {})
        modal-state (r/atom {:open? false :mode nil :row nil :note ""})]
    (fn []
      (let [items    @(rf/subscribe [:revops/cn-appraisals])
            loading? @(rf/subscribe [:revops/cn-appraisals-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            total    (reduce + 0 (map #(or (:commission_amount %) 0) (or items [])))
            finals   (count (filter :is_final (or items [])))
            total-rows  (count (or items []))
            validated (count (filter #(validated-statuses (:status %)) (or items [])))
            validated-pct (if (pos? total-rows)
                            (-> (/ validated total-rows) (* 100) js/Math.round)
                            0)
            on-modal-submit
            (fn [{:keys [mode id note]}]
              (let [m (:month @filter-s) y (:year @filter-s)]
                (case mode
                  :contest (rf/dispatch [:revops/contest-cn-appraisal id note m y])
                  :resolve (rf/dispatch [:revops/resolve-cn-contestation id note m y])
                  nil)))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "vendas" "apuração CN"]
          :title "Apuração Mensal · CN"
          :subtitle (str (count (or items [])) " consultores · " (:month @filter-s) "/" (:year @filter-s))
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/fetch-cn-appraisals
                                      (:month @filter-s) (:year @filter-s)])}
            [layout/icon "refresh" {:width 14 :height 14}] "Buscar"]
           [:button.btn.btn-primary
            {:on-click (fn []
                         (rf/dispatch [:revops/run-cn-appraisal
                                       {:month  (:month @filter-s)
                                        :year   (:year @filter-s)
                                        :inputs (mapv (fn [[cn-id vals]] (merge {:cn_id cn-id} vals))
                                                       @form-inputs)}]))}
            [layout/icon "target" {:width 14 :height 14}] "Rodar apuração"]]}

         [contest-modal {:state modal-state :on-submit on-modal-submit}]

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [m (range 1 13)]
            ^{:key m}
            [:button {:type "button"
                      :class (str "chip" (when (= (str m) (:month @filter-s)) " active"))
                      :aria-pressed (str (= (str m) (:month @filter-s)))
                      :aria-label (str "Mês " m)
                      :on-click #(swap! filter-s assoc :month (str m))}
             (str m)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y ["2025" "2026"]]
            ^{:key y}
            [:button {:type "button"
                      :class (str "chip" (when (= y (:year @filter-s)) " active"))
                      :aria-pressed (str (= y (:year @filter-s)))
                      :on-click #(swap! filter-s assoc :year y)}
             y])]

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "consultores"]
           [:div.kpi-value (str total-rows)]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "comissão total"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "·")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}]
            "% time validou"]
           [:div.kpi-value
            (str validated "/" total-rows)
            [:span {:style {:font-size "13px" :color "var(--fg-3)"
                            :margin-left "8px" :font-family "var(--font-mono)"}}
             (str "(" validated-pct "%)")]]]]

         ;; State machine progress (issue #34) — shows where the cohort
         ;; sits as a whole, taking the most-common status as a proxy.
         (when (seq items)
           (let [statuses (->> items (map :status) (filter some?))
                 dominant (when (seq statuses)
                            (->> statuses frequencies
                                 (sort-by val >) first first))]
             [:div.card {:style {:padding "18px 20px"}}
              [:h3 "Progresso geral"]
              [cn-stepper dominant]
              [:div {:style {:margin-top "10px" :font-size "12px"
                             :color "var(--fg-3)"}}
               (str validated " de " total-rows " CNs validaram own ("
                    validated-pct "%) · "
                    "o Líder pode revisar quando atingir 100%.")]]))

         [:div.callout
          [layout/icon "info" {:width 20 :height 20}]
          [:div {:style {:flex 1}}
           [:strong "Como funciona"]
           [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
            "Preencha os valores realizados nos formulários da equipe (em CN · Metas) e clique em Rodar apuração."]]]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "CN"]
             [:th.center "Score"]
             [:th.right "Mult."]
             [:th.right "Comissão"]
             [:th "Status"]
             [:th.right "Ação"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 6 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? items)
              [:tr [:td {:col-span 6 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma apuração · rode a apuração para gerar"]]

              :else
              (for [row items]
                ^{:key (:id row)}
                (let [next-action (next-status-action (:status row))
                      validating? (= (:status row) "VALIDATING")
                      contested?  (:has_contestation row)]
                  [:tr
                   [:td.name
                    (:cn_name row)
                    (when contested?
                      [:div
                       [:span.badge.badge-review
                        {:style {:font-size "10px" :margin-top "4px"}}
                        "⚠ contestação aberta"]])]
                   [:td.center.num (str (or (pct (:score_final row)) "·") "%")]
                   [:td.right.num (str (or (mult (:multiplicador row)) "·") "x")]
                   [:td.right.strong-num
                    (str "R$ " (or (fmt-int (:commission_amount row)) "·"))]
                   [:td [status->badge (:status row)]]
                   [:td.right
                    (cond
                      (:is_final row)
                      [:span.muted {:style {:font-family "var(--font-mono)"
                                            :font-size "11px"}}
                       "fechado"]

                      contested?
                      [:button.btn.btn-secondary.btn-sm
                       {:on-click #(reset! modal-state
                                          {:open? true :mode :resolve
                                           :row row :note ""})}
                       "Resolver contestação"]

                      validating?
                      [:div {:style {:display "flex" :gap "6px"
                                     :justify-content "flex-end"}}
                       [:button.btn.btn-secondary.btn-sm
                        {:on-click #(reset! modal-state
                                           {:open? true :mode :contest
                                            :row row :note ""})}
                        "Contestar"]
                       (when next-action
                         [:button.btn.btn-primary.btn-sm
                          {:on-click #(rf/dispatch
                                       [:revops/transition-cn-appraisal
                                        (:id row) (second next-action)
                                        (:month @filter-s) (:year @filter-s)])}
                          (first next-action)])]

                      next-action
                      [:button.btn.btn-primary.btn-sm
                       {:on-click #(rf/dispatch
                                    [:revops/transition-cn-appraisal
                                     (:id row) (second next-action)
                                     (:month @filter-s) (:year @filter-s)])}
                       (first next-action)]

                      :else nil)]])))]]]]))))
