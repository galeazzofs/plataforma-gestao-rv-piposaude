(ns app.views.revops.quarterly-cycle
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Unified QuarterlyCycle page — feeds from
;; GET /api/v1/quarterly-cycles/:id (issue #37 aggregator).

(def ^:private steps
  ["DRAFT" "CALCULATING" "VALIDATING" "LIDER_REVIEW" "REVOPS_REVIEW" "LOCKED"])

(def ^:private step-labels
  {"DRAFT"         "Draft"
   "CALCULATING"   "Calculating"
   "VALIDATING"    "Validating"
   "LIDER_REVIEW"  "Líder Review"
   "REVOPS_REVIEW" "RevOps Review"
   "LOCKED"        "Locked"})

(def ^:private component-labels
  {"ev_quarter"          "Comissão EV"
   "ev_quarterly_bonus"  "Bônus EV"
   "cn_monthly"          "Comissão CN (mês final)"
   "cn_quarterly_bonus"  "Bônus CN trimestral"
   "leadership"          "Comissão Liderança"})

(def ^:private component-routes
  {"ev_quarter"          :revops/appraisal
   "ev_quarterly_bonus"  :revops/ev-bonus
   "cn_monthly"          :revops/cn-appraisal
   "cn_quarterly_bonus"  :revops/cn-quarterly-bonus
   "leadership"          :revops/leadership})

(defn- status->badge [status]
  (case status
    "PENDING"       [:span.badge.badge-locked "Pendente"]
    "DRAFT"         [:span.badge.badge-draft "Draft"]
    "CALCULATING"   [:span.badge.badge-calc "Calculating"]
    "VALIDATING"    [:span.badge.badge-validating "Validating"]
    "LIDER_REVIEW"  [:span.badge.badge-review "Líder Review"]
    "REVOPS_REVIEW" [:span.badge.badge-review "RevOps Review"]
    "LOCKED"        [:span.badge.badge-paid "Locked"]
    [:span.badge.badge-locked (or status "·")]))

(defn- stepper [current-status]
  (let [idx (max 0 (.indexOf (clj->js steps) (or current-status "DRAFT")))]
    [:div.stepper
     (for [[i s] (map-indexed vector steps)
           :let [done?    (< i idx)
                 current? (= i idx)]]
       ^{:key s}
       [:<>
        [:div.stepper-stack
         [:div {:class (str "step" (cond done? " done" current? " current"))}
          [:div.step-dot (str (inc i))]]
         [:div.step-label (step-labels s)]]
        (when (< i (dec (count steps)))
          [:div.step-line])])]))

(defn- component-card-for-team [team component-key component]
  [:div.card
   [:div.card-head
    [:div
     [:h4 (component-labels component-key)]
     [:div.card-sub (str "Time: " (:team_name team))]]
    [status->badge (or (:status component) "PENDING")]]
   [:div {:style {:padding "12px 0"}}
    (let [validations-total (:validations_total component)
          validations-done  (:validations_done component)
          rows              (:rows component)
          final             (:final component)
          month             (:month component)
          contest?          (:has_contestation component)]
      [:<>
       (cond
         (and validations-total (pos? validations-total))
         [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
          (str validations-done " / " validations-total " validações concluídas")]

         (and rows (pos? rows))
         [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
          (str final " / " rows " final"
               (when month (str " · mês " month)))]

         month
         [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
          (str "mês " month)]

         :else
         [:div.muted {:style {:font-family "var(--font-mono)" :font-size "12px"}}
          "—"])
       (when contest?
         [:span.badge.badge-review {:style {:margin-top "6px"}}
          "⚠ contestação aberta"])])]
   [:div {:style {:display "flex" :gap "8px" :margin-top "8px"}}
    (when-let [route (component-routes component-key)]
      [:button.btn.btn-secondary.btn-sm
       {:on-click #(rf/dispatch [:navigate route])}
       "Abrir"])]])

(defn- next-quarter [{:keys [quarter year]}]
  (if (< quarter 4)
    {:quarter (inc quarter) :year year}
    {:quarter 1 :year (inc year)}))

(defn quarter-for-date [date]
  (inc (quot (.getMonth date) 3)))

(defn current-cycle-suggestion
  ([] (current-cycle-suggestion (js/Date.)))
  ([date]
   {:quarter (quarter-for-date date)
    :year (.getFullYear date)}))

(defn suggest-cycle
  "Suggest the cycle that should be opened next.
   With no existing cycles, default to the current quarter. If the most recent
   cycle is LOCKED and there's no cycle yet for the following quarter, suggest
   that following quarter."
  ([cycles last-cycle]
   (suggest-cycle cycles last-cycle (js/Date.)))
  ([cycles last-cycle today]
   (cond
     (empty? (or cycles []))
     (current-cycle-suggestion today)

     (and last-cycle (= "LOCKED" (:status last-cycle)))
     (let [{:keys [quarter year] :as nq} (next-quarter last-cycle)
           already? (some #(and (= (:quarter %) quarter)
                                 (= (:year %) year))
                          cycles)]
       (when-not already? nq)))))

(defn- header-banner [cycles cycle suggestion]
  [:<>
   (when (and (not cycle) suggestion)
     [:div.callout
      [layout/icon "info" {:width 20 :height 20}]
      [:div {:style {:flex 1}}
       [:strong (str "Q" (:quarter suggestion) "/" (:year suggestion)
                     " pronto para apurar")]
       [:div {:style {:font-size "13px" :color "var(--fg-3)"}}
        (if (empty? (or cycles []))
          "Abra o ciclo trimestral atual para começar."
          "O trimestre anterior está fechado. Abra o ciclo trimestral para começar.")]]
      [:button.btn.btn-primary.btn-sm
       {:on-click #(rf/dispatch [:revops/open-quarterly-cycle suggestion])}
       (str "Abrir Q" (:quarter suggestion) "/" (:year suggestion))]])])

(defn- pick-cycle
  "Default to the most-recent OPEN cycle, falling back to the latest row."
  [cycles]
  (let [sorted (->> (or cycles [])
                    (sort-by (juxt :year :quarter) #(compare %2 %1)))]
    (or (first (filter #(= "OPEN" (:status %)) sorted))
        (first sorted))))

(defn page []
  (rf/dispatch [:revops/fetch-quarterly-cycles])
  (fn []
    (let [cycles     @(rf/subscribe [:revops/quarterly-cycles])
          loading?   @(rf/subscribe [:revops/quarterly-cycle-loading?])
          user       @(rf/subscribe [:auth/current-user])
          route      @(rf/subscribe [:current-route-name])
          target     (pick-cycle cycles)
          last-cycle (first (->> (or cycles [])
                                 (sort-by (juxt :year :quarter) #(compare %2 %1))))
          suggestion (suggest-cycle cycles last-cycle)
          cycle-id   (:id target)
          detail     @(rf/subscribe [:revops/quarterly-cycle])
          cycle      (when (and detail target (= (:id detail) cycle-id)) detail)]
      (when (and cycle-id (or (not detail) (not= (:id detail) cycle-id)))
        (rf/dispatch [:revops/fetch-quarterly-cycle-detail cycle-id]))
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "admin" "ciclo trimestral"]
        :title (if cycle
                 (str "Q" (:quarter cycle) "/" (:year cycle)
                      " · " (case (:status cycle)
                              "OPEN" "Em andamento"
                              "LOCKED" "Fechado"
                              (:status cycle)))
                 "Ciclo Trimestral")
        :subtitle "Visão unificada dos 5 componentes da apuração"
        :header-actions nil}

       [header-banner cycles cycle suggestion]

       (cond
         loading?
         [:div.card [:div {:style {:padding "32px" :text-align "center"
                                    :color "var(--fg-3)"}} "Carregando…"]]

         (and (not cycle) (empty? (or cycles [])))
         [:div.card
          [:div.empty
           [:h4 "Nenhum ciclo aberto"]
           [:p "Use o botão acima para abrir o próximo ciclo trimestral."]]]

         (not cycle)
         [:div.card [:div {:style {:padding "32px" :text-align "center"
                                    :color "var(--fg-3)"}}
                     "Selecione um ciclo para ver os detalhes."]]

         :else
         [:<>
          ;; Stepper using the OPEN cycle's status as the cohort summary.
          [:div.card {:style {:padding "18px 20px"}}
           [:h3 "Progresso geral"]
           [stepper (or (:status cycle) "OPEN")]]

          ;; Component cards, grouped per team.
          (for [team (:teams cycle)]
            ^{:key (or (:team_id team) (:team_name team))}
            [:div {:style {:margin-top "20px"}}
             [:h3 {:style {:margin-bottom "8px"}}
              (:team_name team)]
             [:div.muted {:style {:font-family "var(--font-mono)"
                                   :font-size "11px"
                                   :margin-bottom "12px"}}
              (str (:ev_count team) " EVs · " (:cn_count team) " CNs")]
             [:div.form-grid.-three
              (for [[k label] component-labels]
                ^{:key k}
                [component-card-for-team team k
                 (get-in team [:components (keyword k)]
                          (get-in team [:components k]))])]])])])))
