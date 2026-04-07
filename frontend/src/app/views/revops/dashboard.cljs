(ns app.views.revops.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.auth.subs]))

(def sidebar-items
  [{:key :revops/dashboard        :label "Dashboard"         :icon "🏠" :route :revops/dashboard}
   {:key :revops/policies         :label "Apólices"          :icon "📄" :route :revops/policies}
   {:key :revops/users            :label "Usuários"          :icon "👤" :route :revops/users}
   {:key :revops/teams            :label "Times"             :icon "👥" :route :revops/teams}
   {:key :revops/goals            :label "Metas"             :icon "🎯" :route :revops/goals}
   {:key :revops/commission-table :label "Tabela %"          :icon "%" :route :revops/commission-table}
   {:key :revops/financial        :label "Upload Financeiro" :icon "📁" :route :revops/financial}
   {:key :revops/appraisal        :label "Apuração"          :icon "⚙️" :route :revops/appraisal}
   {:key :revops/contestations    :label "Contestações"      :icon "⚠️" :route :revops/contestations}
   {:key :revops/sync-status      :label "Sync"              :icon "🔄" :route :revops/sync-status}
   {:key :revops/audit-log        :label "Audit Log"         :icon "📋" :route :revops/audit-log}
   {:key :revops/settings         :label "Configurações"     :icon "⚙️" :route :revops/settings}])

(defn stat-action-card [{:keys [label value icon on-click accent]}]
  (let [accent-bg    (case accent
                       :success t/success-light
                       :warning t/warning-light
                       :error   t/error-light
                       :info    "#DBEAFE"
                       t/beige-100)
        accent-color (case accent
                       :success t/success-dark
                       :warning t/warning-dark
                       :error   t/error-dark
                       :info    t/blue-700
                       t/beige-700)]
    [:div {:style {:background t/bg-card
                   :border-radius (:lg t/border-radius)
                   :padding "24px"
                   :box-shadow (:card t/shadows)
                   :border (str "1px solid " t/border-default)
                   :cursor (when on-click "pointer")
                   :transition (str "all " t/transition-default)
                   :display "flex"
                   :flex-direction "column"
                   :gap "12px"}
           :on-click on-click}
     (when icon
       [:div {:style {:width "44px" :height "44px" :border-radius (:lg t/border-radius)
                      :background accent-bg :display "flex" :align-items "center"
                      :justify-content "center" :font-size "20px" :color accent-color}}
        icon])
     [:div
      [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary
                     :text-transform "uppercase" :letter-spacing "0.06em"
                     :font-weight (:medium t/font-weights) :margin-bottom "6px"}} label]
      [:div {:style {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights)
                     :color t/text-primary :line-height "1.1"}} value]]
     (when on-click
       [:span {:style {:font-size (:xs t/font-sizes) :color accent-color
                       :display "flex" :align-items "center" :gap "4px"
                       :font-weight (:medium t/font-weights)}}
        "Ver detalhes"])]))

(defn quick-action-card [{:keys [label description icon on-click]}]
  [:div {:style {:background t/bg-card
                 :border-radius (:lg t/border-radius)
                 :padding "20px"
                 :box-shadow (:card t/shadows)
                 :border (str "1px solid " t/border-default)
                 :cursor "pointer"
                 :transition (str "all " t/transition-fast)
                 :display "flex"
                 :align-items "center"
                 :gap "14px"}
         :on-click on-click}
   [:div {:style {:width "44px" :height "44px" :border-radius (:md t/border-radius)
                  :background t/bg-main :display "flex" :align-items "center"
                  :justify-content "center" :font-size "22px" :flex-shrink "0"}}
    icon]
   [:div
    [:div {:style {:font-size (:sm t/font-sizes) :font-weight (:semibold t/font-weights)
                   :color t/text-primary}} label]
    (when description
      [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :margin-top "2px"}} description])]])

(defn revops-dashboard-page []
  (rf/dispatch [:revops/fetch-appraisals])
  (rf/dispatch [:revops/fetch-sync-status])
  (rf/dispatch [:revops/fetch-contestations])
  (fn []
    (let [appraisals    @(rf/subscribe [:revops/appraisals])
          sync-status   @(rf/subscribe [:revops/sync-status])
          contestations @(rf/subscribe [:revops/contestations])
          user          @(rf/subscribe [:auth/current-user])
          route         @(rf/subscribe [:current-route-name])
          active-appraisal (first (filter #(not= (:status %) "LOCKED") (or appraisals [])))
          pending-count (count (filter #(= (:status %) "CONTESTED") (or contestations [])))]
      [layout/page-shell
       {:sidebar-items sidebar-items
        :current-route route
        :user          user
        :title         "Admin Dashboard"
        :subtitle      "Visão geral do sistema de comissões"}

       ;; Status cards
       [:div {:style {:display "grid" :grid-template-columns "repeat(auto-fit, minmax(260px, 1fr))" :gap "20px"}}
        [stat-action-card
         {:label    "Apuracao Ativa"
          :value    (if active-appraisal
                      (str "Q" (:quarter active-appraisal) "/" (:year active-appraisal))
                      "Nenhuma")
          :icon     "⚙"
          :accent   (if active-appraisal :info :default)
          :on-click #(rf/dispatch [:navigate :revops/appraisal])}]
        [stat-action-card
         {:label    "Contestacoes Pendentes"
          :value    (str pending-count)
          :icon     "!"
          :accent   (if (pos? pending-count) :warning :success)
          :on-click #(rf/dispatch [:navigate :revops/contestations])}]
        [stat-action-card
         {:label  "Ultimo Sync"
          :value  (or (:last_sync sync-status) "Nunca")
          :icon   "↻"
          :accent :default}]]

       ;; Quick actions
       [:div
        [:h3 {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights)
                      :margin "0 0 16px" :color t/text-primary}} "Ações Rápidas"]
        [:div {:style {:display "grid" :grid-template-columns "repeat(auto-fit, minmax(220px, 1fr))" :gap "12px"}}
         [quick-action-card
          {:label       "Gerenciar Apuração"
           :description "Fluxo de cálculo e aprovação"
           :icon        "⚙️"
           :on-click    #(rf/dispatch [:navigate :revops/appraisal])}]
         [quick-action-card
          {:label       "Upload Financeiro"
           :description "Importar dados via XLSX"
           :icon        "📁"
           :on-click    #(rf/dispatch [:navigate :revops/financial])}]
         [quick-action-card
          {:label       "Sincronizar HubSpot"
           :description "Atualizar dados de negócios"
           :icon        "🔄"
           :on-click    #(rf/dispatch [:revops/trigger-sync])}]
         [quick-action-card
          {:label       "Gerenciar Usuários"
           :description "Usuários e permissões"
           :icon        "👤"
           :on-click    #(rf/dispatch [:navigate :revops/users])}]]]])))
