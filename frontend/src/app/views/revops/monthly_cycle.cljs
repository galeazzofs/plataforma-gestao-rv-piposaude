(ns app.views.revops.monthly-cycle
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Unified MonthlyCycle page — feeds from
;; GET /api/v1/monthly-cycles/:id (cycle aggregator).
;;
;; The cycle runs the apuração sequence: Apuração EV → Apuração CN →
;; (quarter-end months only) Bônus CN, Bônus EV e Bônus Liderança.

(def ^:private steps
  ["DRAFT" "CALCULATING" "VALIDATING" "LIDER_REVIEW" "REVOPS_REVIEW" "LOCKED"])

(def ^:private step-labels
  {"DRAFT"         "Draft"
   "CALCULATING"   "Calculating"
   "VALIDATING"    "Validating"
   "LIDER_REVIEW"  "Líder Review"
   "REVOPS_REVIEW" "RevOps Review"
   "LOCKED"        "Locked"})

(def ^:private base-sequence
  [["ev_apuracao" "Apuração EV"]
   ["cn_apuracao" "Apuração CN"]])

(def ^:private quarter-end-sequence
  [["cn_bonus" "Bônus CN"]
   ["ev_bonus" "Bônus EV"]
   ["leadership_bonus" "Bônus Liderança"]])

(defn components-for
  "Ordered [key label] sequence for a cycle. The quarterly bonuses only
   appear on the last month of each quarter."
  [cycle]
  (if (:is_quarter_end cycle)
    (into base-sequence quarter-end-sequence)
    base-sequence))

(def ^:private component-routes
  {"ev_apuracao"      :revops/appraisal
   "cn_apuracao"      :revops/cn-appraisal
   "cn_bonus"         :revops/cn-quarterly-bonus
   "ev_bonus"         :revops/ev-bonus
   "leadership_bonus" :revops/leadership})

(def ^:private month-names
  ["Janeiro" "Fevereiro" "Março" "Abril" "Maio" "Junho"
   "Julho" "Agosto" "Setembro" "Outubro" "Novembro" "Dezembro"])

(defn cycle-label [{:keys [month year]}]
  (str (nth month-names (dec month) month) "/" year))

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

(defn- component-card-for-team [team step-number label component-key component]
  [:div.card
   [:div.card-head
    [:div
     [:h4 (str step-number " · " label)]
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

(defn- next-month [{:keys [month year]}]
  (if (< month 12)
    {:month (inc month) :year year}
    {:month 1 :year (inc year)}))

(defn current-cycle-suggestion
  ([] (current-cycle-suggestion (js/Date.)))
  ([date]
   {:month (inc (.getMonth date))
    :year (.getFullYear date)}))

(defn suggest-cycle
  "Suggest the cycle that should be opened next.
   With no existing cycles, default to the current month. If the most recent
   cycle is LOCKED and there's no cycle yet for the following month, suggest
   that following month."
  ([cycles last-cycle]
   (suggest-cycle cycles last-cycle (js/Date.)))
  ([cycles last-cycle today]
   (cond
     (empty? (or cycles []))
     (current-cycle-suggestion today)

     (and last-cycle (= "LOCKED" (:status last-cycle)))
     (let [{:keys [month year] :as nm} (next-month last-cycle)
           already? (some #(and (= (:month %) month)
                                 (= (:year %) year))
                          cycles)]
       (when-not already? nm)))))

(defn- header-banner [cycles cycle suggestion]
  [:<>
   (when (and (not cycle) suggestion)
     [:div.callout
      [layout/icon "info" {:width 20 :height 20}]
      [:div {:style {:flex 1}}
       [:strong (str (cycle-label suggestion) " pronto para apurar")]
       [:div {:style {:font-size "13px" :color "var(--fg-3)"}}
        (if (empty? (or cycles []))
          "Abra o ciclo mensal atual para começar."
          "O mês anterior está fechado. Abra o ciclo mensal para começar.")]]
      [:button.btn.btn-primary.btn-sm
       {:on-click #(rf/dispatch [:revops/open-monthly-cycle suggestion])}
       (str "Abrir " (cycle-label suggestion))]])])

(defn- pick-cycle
  "Default to the most-recent OPEN cycle, falling back to the latest row."
  [cycles]
  (let [sorted (->> (or cycles [])
                    (sort-by (juxt :year :month) #(compare %2 %1)))]
    (or (first (filter #(= "OPEN" (:status %)) sorted))
        (first sorted))))

(defn- delete-cycle-btn [cycle]
  (let [{:keys [id status]} cycle
        locked? (= "LOCKED" status)]
    [:button.btn.btn-danger.btn-sm
     {:disabled locked?
      :title    (if locked?
                  "Ciclos LOCKED não podem ser excluídos."
                  "Excluir este ciclo mensal.")
      :on-click #(when (js/confirm
                        (str "Tem certeza que deseja excluir o ciclo "
                             (cycle-label cycle) "? "
                             "Esta ação não pode ser desfeita."))
                   (rf/dispatch [:revops/delete-monthly-cycle id]))}
     "Excluir ciclo"]))

(defn page []
  (rf/dispatch [:revops/fetch-monthly-cycles])
  (fn []
    (let [cycles     @(rf/subscribe [:revops/monthly-cycles])
          loading?   @(rf/subscribe [:revops/monthly-cycle-loading?])
          user       @(rf/subscribe [:auth/current-user])
          route      @(rf/subscribe [:current-route-name])
          target     (pick-cycle cycles)
          last-cycle (first (->> (or cycles [])
                                 (sort-by (juxt :year :month) #(compare %2 %1))))
          suggestion (suggest-cycle cycles last-cycle)
          cycle-id   (:id target)
          detail     @(rf/subscribe [:revops/monthly-cycle])
          cycle      (when (and detail target (= (:id detail) cycle-id)) detail)]
      (when (and cycle-id (or (not detail) (not= (:id detail) cycle-id)))
        (rf/dispatch [:revops/fetch-monthly-cycle-detail cycle-id]))
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "admin" "ciclo mensal"]
        :title (if cycle
                 (str (cycle-label cycle)
                      " · " (case (:status cycle)
                              "OPEN" "Em andamento"
                              "LOCKED" "Fechado"
                              (:status cycle)))
                 "Ciclo Mensal")
        :subtitle "Sequência da apuração: EVs, CNs e — no fechamento do trimestre — os bônus"
        :header-actions (when cycle (delete-cycle-btn cycle))}

       [header-banner cycles cycle suggestion]

       (cond
         loading?
         [:div.card [:div {:style {:padding "32px" :text-align "center"
                                    :color "var(--fg-3)"}} "Carregando…"]]

         (and (not cycle) (empty? (or cycles [])))
         [:div.card
          [:div.empty
           [:h4 "Nenhum ciclo aberto"]
           [:p "Use o botão acima para abrir o próximo ciclo mensal."]]]

         (not cycle)
         [:div.card [:div {:style {:padding "32px" :text-align "center"
                                    :color "var(--fg-3)"}}
                     "Selecione um ciclo para ver os detalhes."]]

         :else
         (let [comps (components-for cycle)]
           [:<>
            ;; Stepper using the OPEN cycle's status as the cohort summary.
            [:div.card {:style {:padding "18px 20px"}}
             [:h3 "Progresso geral"]
             [stepper (or (:status cycle) "OPEN")]]

            (when (:is_quarter_end cycle)
              [:div.callout {:style {:margin-top "16px"}}
               [layout/icon "info" {:width 20 :height 20}]
               [:div {:style {:flex 1}}
                [:strong (str "Fechamento do Q" (:quarter cycle))]
                [:div {:style {:font-size "13px" :color "var(--fg-3)"}}
                 "Último mês do trimestre: além das apurações, este ciclo inclui Bônus CN, Bônus EV e Bônus Liderança."]]])

            ;; Component cards, grouped per team, in sequence order.
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
                (for [[i [k label]] (map-indexed vector comps)]
                  ^{:key k}
                  [component-card-for-team team (inc i) label k
                   (get-in team [:components (keyword k)]
                            (get-in team [:components k]))])]])]))])))
