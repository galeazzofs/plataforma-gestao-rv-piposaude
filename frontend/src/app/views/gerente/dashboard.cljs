(ns app.views.gerente.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.auth.subs]))

(def sidebar-items
  [{:key :gerente/dashboard :label "Dashboard (Time)" :icon "👥" :route :gerente/dashboard}])

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(def team-columns
  [{:key :name          :label "EV"            :sortable true}
   {:key :achievement   :label "Atingimento"   :sortable true
    :render (fn [row]
              (let [pct (or (:achievement_pct row) 0)
                    color (cond (>= pct 100) t/success-default
                                (>= pct 50)  t/warning-default
                                :else        t/error-default)]
                [:span {:style {:color color :font-weight (:semibold t/font-weights)}}
                 (str (.toFixed pct 1) "%")]))}
   {:key :saldo         :label "Saldo"         :sortable true
    :render (fn [row] (fmt-brl (:saldo row)))}
   {:key :commission_total :label "Comissão Total" :sortable true
    :render (fn [row] (fmt-brl (:commission_total row)))}
   {:key :status        :label "Status"        :sortable false
    :render (fn [row] [badge/status-badge {:status (:appraisal_status row)}])}
   {:key :actions       :label ""              :sortable false
    :render (fn [row]
              [btn/button
               {:variant  :ghost
                :size     :sm
                :on-click #(rf/dispatch [:navigate! [:gerente/ev-detail {:ev-id (:id row)}]])}
               "Ver detalhes →"])}])

(defn team-summary [members]
  (let [total-commission (reduce + 0 (map #(or (:commission_total %) 0) members))
        avg-achievement  (if (empty? members)
                           0
                           (/ (reduce + 0 (map #(or (:achievement_pct %) 0) members))
                              (count members)))]
    [:div {:style {:display "grid"
                   :grid-template-columns "repeat(3, 1fr)"
                   :gap "24px"
                   :margin-bottom "32px"}}
     [cards/stat-card
      {:label    "Membros no Time"
       :value    (str (count members))
       :subtitle "EVs ativos"}]
     [cards/stat-card
      {:label    "Comissão Total (Time)"
       :value    (fmt-brl total-commission)
       :subtitle "Soma de todos os EVs"}]
     [cards/progress-card
      {:label      "Atingimento Médio"
       :percentage avg-achievement}]]))

(defn gerente-dashboard-page []
  (rf/dispatch [:gerente/fetch-team])
  (fn []
    (let [members  @(rf/subscribe [:gerente/team-members])
          loading? @(rf/subscribe [:gerente/loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items sidebar-items
        :current-route route
        :user          user
        :title         "Dashboard — Time"
        :subtitle      "Visão consolidada da equipe"}

       (if loading?
         [:div {:style {:color t/text-secondary}} "Carregando..."]
         [team-summary (or members [])])

       [cards/card {}
        [tbl/data-table
         {:columns       team-columns
          :rows          (or members [])
          :empty-message (if loading? "Carregando..." "Nenhum membro encontrado")}]]])))
