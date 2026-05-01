(ns app.views.revops.appraisal
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

;; Apurações — list + active stepper, mirroring the design's "Apurações" screen.

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- status->badge [status]
  (case status
    "DRAFT"      [:span.badge.badge-draft "Draft"]
    "CALCULATING"[:span.badge.badge-calc "Calculating"]
    "REVIEWING"  [:span.badge.badge-review "Reviewing"]
    "VALIDATING" [:span.badge.badge-validating "Validating"]
    "APPROVED"   [:span.badge.badge-approved "Approved"]
    "LOCKED"     [:span.badge.badge-locked "Locked"]
    [:span.badge.badge-locked (or status "—")]))

(def ^:private steps ["DRAFT" "CALCULATING" "REVIEWING" "VALIDATING" "APPROVED" "LOCKED"])
(def ^:private step-labels
  {"DRAFT" "Draft" "CALCULATING" "Calculating" "REVIEWING" "Reviewing"
   "VALIDATING" "Validating" "APPROVED" "Approved" "LOCKED" "Locked"})

(defn- stepper [current]
  (let [idx (max 0 (.indexOf (clj->js steps) (or current "DRAFT")))]
    [:div.stepper
     (for [[i s] (map-indexed vector steps)
           :let [done?    (< i idx)
                 current? (= i idx)]]
       ^{:key s}
       [:<>
        [:div.stepper-stack
         [:div {:class (str "step" (cond done? " done" current? " current"))}
          [:div.step-dot
           (if done?
             [:svg {:style {:width "13px" :height "13px" :color "#fff"} :aria-hidden true}
              [:use {:href "#i-check"}]]
             (str (inc i)))]]
         [:div.step-label
          {:style (cond done?    {:color "var(--fg-1)"}
                        current? {:color "var(--fg-1)" :font-weight 600})}
          (step-labels s)]]
        (when (< i (dec (count steps)))
          [:div.step-line
           {:style (when (or done? (and current? (>= i (dec idx))))
                     {:background "var(--success-dark)"})}])])]))

(defn- new-appraisal-modal [_]
  (let [form (r/atom {:quarter "1" :year "2026"})]
    (fn [{:keys [open? on-close]}]
      [modal/modal {:open? open? :on-close on-close :title "Nova Apuração" :size :sm}
       [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
        [inputs/select
         {:label "Trimestre" :value (:quarter @form)
          :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                    {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
          :on-change #(swap! form assoc :quarter %)}]
        [inputs/select
         {:label "Ano" :value (:year @form)
          :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
          :on-change #(swap! form assoc :year %)}]
        [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
         [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
         [btn/button {:variant :primary
                      :on-click (fn []
                                  (rf/dispatch [:revops/create-appraisal @form])
                                  (on-close))}
          "Criar"]]]])))

(defn- active-card [active]
  (let [period (when active (str "Q" (:quarter active) "/" (:year active)))
        status (or (:status active) "REVIEWING")]
    [:div.card
     [:div.card-head
      [:div
       [:div {:style {:font-family "var(--font-mono)" :font-size "11px"
                      :color "var(--fg-3)" :text-transform "lowercase"}}
        "apuração ativa"]
       [:h2 {:style {:font-family "var(--font-display)" :font-weight 400 :font-size "24px" :margin-top "2px"}}
        (str (or period "—") " · em revisão")]]
      [:div.card-actions
       [status->badge status]
       (when active
         [:button.btn.btn-primary.btn-sm
          {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id (:id active)}]])}
          "Revisar valores " [layout/icon "arrow-right" {:width 12 :height 12}]])]]
     [stepper status]
     [:div {:style {:display "grid" :grid-template-columns "repeat(4,1fr)" :gap "16px"
                    :border-top "1px solid var(--border-subtle)" :padding-top "16px"}}
      [:div
       [:div {:style {:font-family "var(--font-mono)" :font-size "11px"
                      :color "var(--fg-3)" :text-transform "lowercase"}}
        "EVs apurados"]
       [:div {:style {:font-family "var(--font-display)" :font-size "24px" :color "var(--fg-1)"}}
        (str (or (:ev_count active) 14))]]
      [:div
       [:div {:style {:font-family "var(--font-mono)" :font-size "11px"
                      :color "var(--fg-3)" :text-transform "lowercase"}}
        "comissão total"]
       [:div {:style {:font-family "var(--font-display)" :font-size "24px" :color "var(--fg-1)"}}
        (str "R$ " (or (fmt-int (:total_amount active)) "412.300"))]]
      [:div
       [:div {:style {:font-family "var(--font-mono)" :font-size "11px"
                      :color "var(--fg-3)" :text-transform "lowercase"}}
        "divergências"]
       [:div {:style {:font-family "var(--font-display)" :font-size "24px" :color "var(--warning-dark)"}}
        (str (or (:contestation_count active) 7))]]
      [:div
       [:div {:style {:font-family "var(--font-mono)" :font-size "11px"
                      :color "var(--fg-3)" :text-transform "lowercase"}}
        "prazo p/ encerrar"]
       [:div {:style {:font-family "var(--font-display)" :font-size "24px" :color "var(--fg-1)"}}
        "12 dias"]]]]))

(defn- delete-btn [id]
  [:button.btn.btn-danger.btn-sm
   {:on-click (fn [e]
                (.stopPropagation e)
                (when (js/confirm "Tem certeza? Isso vai apagar a apuração e resetar todos os matches de NFs.")
                  (rf/dispatch [:revops/delete-appraisal id])))}
   "Deletar"])

(defn- step-actions [{:keys [status id] :as _row}]
  (case status
    "DRAFT"
    [:<>
     [:button.btn.btn-primary.btn-sm
      {:on-click #(rf/dispatch [:revops/run-appraisal id])}
      "Iniciar"]
     [delete-btn id]]

    "CALCULATING"
    [:<>
     [:button.btn.btn-primary.btn-sm
      {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
      "Revisar"]
     [delete-btn id]]

    "REVIEWING"
    [:<>
     [:button.btn.btn-primary.btn-sm
      {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
      "Revisar"]
     [delete-btn id]]

    "VALIDATING"
    [:button.btn.btn-secondary.btn-sm
     {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
     "Acompanhar"]

    "APPROVED"
    [:button.btn.btn-primary.btn-sm
     {:on-click #(rf/dispatch [:revops/approve-appraisal-payment id])}
     "Liberar"]

    "LOCKED"
    [:button.btn.btn-ghost.btn-sm
     {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
     "Ver"]

    [:button.btn.btn-ghost.btn-sm
     {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id id}]])}
     "Ver"]))

(defn appraisal-page []
  (rf/dispatch [:revops/fetch-appraisals])
  (let [modal-open? (r/atom false)]
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            user       @(rf/subscribe [:auth/current-user])
            route      @(rf/subscribe [:current-route-name])
            sorted     (->> appraisals (sort-by (juxt :year :quarter) #(compare %2 %1)))
            active     (first (filter #(not= (:status %) "LOCKED") sorted))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "admin" "apurações"]
          :title "Apurações"
          :subtitle "Controle do fluxo de cálculo e aprovação"
          :header-actions
          [[:button.btn.btn-primary
            {:on-click #(reset! modal-open? true)}
            [layout/icon "plus" {:width 14 :height 14}] "Nova apuração"]]}

         [active-card active]

         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "24px 24px 16px"}}
           [:h3 "Histórico"]
           [:div.card-sub
            (str (count sorted) " apuraç" (if (= 1 (count sorted)) "ão" "ões") " criada"
                 (when (not= 1 (count sorted)) "s"))]]
          [:table.table
           [:thead
            [:tr
             [:th "Período"]
             [:th "Status"]
             [:th.center "EVs"]
             [:th.right "Total"]
             [:th "Criada em"]
             [:th "Encerrada em"]
             [:th.right "Ações"]]]
           [:tbody
            (if (empty? sorted)
              [:tr [:td {:col-span 7 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma apuração encontrada"]]
              (for [a sorted]
                ^{:key (:id a)}
                [:tr
                 [:td.name.num (str "Q" (:quarter a) "/" (:year a))]
                 [:td [status->badge (:status a)]]
                 [:td.center.num (str (or (:ev_count a) "—"))]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:total_amount a)) "—"))]
                 [:td.num.muted (or (:created_at_short a) "—")]
                 [:td.num.muted (or (:closed_at_short a) "—")]
                 [:td.right [step-actions a]]]))]]]

         [new-appraisal-modal {:open? @modal-open? :on-close #(reset! modal-open? false)}]]))))
