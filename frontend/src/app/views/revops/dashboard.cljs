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

(defn pending-action-card [label value on-click]
  [cards/card {:style {:cursor "pointer"} }
   [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"}}
    [:div
     [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase"}} label]
     [:div {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights) :margin-top "4px"}} value]]
    (when on-click
      [btn/button {:variant :ghost :size :sm :on-click on-click} "Ver →"])]])

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
        :subtitle      "Visão geral do sistema"}

       ;; Status cards
       [:div {:style {:display "grid" :grid-template-columns "repeat(3, 1fr)" :gap "24px" :margin-bottom "32px"}}
        [pending-action-card
         "Apuração Ativa"
         (if active-appraisal
           [badge/status-badge {:status (:status active-appraisal)}]
           "—")
         #(rf/dispatch [:navigate! :revops/appraisal])]
        [pending-action-card
         "Contestações Pendentes"
         (str pending-count)
         #(rf/dispatch [:navigate! :revops/contestations])]
        [cards/card {}
         [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
          [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase"}} "Último Sync"]
          [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:semibold t/font-weights)}}
           (or (:last_sync sync-status) "Nunca")]
          (when-let [cnt (:records_synced sync-status)]
            [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
             (str cnt " registros")])]]]

       ;; Quick actions
       [:div
        [:h3 {:style {:font-size (:lg t/font-sizes) :font-weight (:semibold t/font-weights) :margin-bottom "16px"}}
         "Ações Rápidas"]
        [:div {:style {:display "flex" :gap "12px" :flex-wrap "wrap"}}
         [btn/button {:variant :secondary :on-click #(rf/dispatch [:navigate! :revops/appraisal])}
          "Gerenciar Apuração"]
         [btn/button {:variant :secondary :on-click #(rf/dispatch [:navigate! :revops/financial])}
          "Upload Financeiro"]
         [btn/button {:variant :secondary :on-click #(rf/dispatch [:revops/trigger-sync])}
          "Sincronizar Agora"]
         [btn/button {:variant :secondary :on-click #(rf/dispatch [:navigate! :revops/users])}
          "Gerenciar Usuários"]]]])))
