(ns app.views.revops.sync-status
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.buttons :as btn]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn sync-status-page []
  (rf/dispatch [:revops/fetch-sync-status])
  (fn []
    (let [status   @(rf/subscribe [:revops/sync-status])
          loading? @(rf/subscribe [:revops/sync-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items revops-shell/sidebar-items
        :current-route route
        :user          user
        :title         "Status do Sync"
        :subtitle      "Monitorar sincronização com HubSpot"
        :header-actions
        [btn/button
         {:variant  :primary
          :loading  loading?
          :on-click #(rf/dispatch [:revops/trigger-sync])}
         "Sincronizar Agora"]}

       [cards/card {}
        (if loading?
          [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Carregando..."]
          (if (nil? status)
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Nenhum dado de sync disponível"]
            [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
             ;; Last sync info
             [:div {:style {:display "grid" :grid-template-columns "1fr 1fr 1fr" :gap "16px"}}
              [:div
               [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase"}}
                "Último Sync"]
               [:div {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights) :margin-top "4px"}}
                (or (:last_sync status) "Nunca")]]
              [:div
               [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase"}}
                "Registros Sincronizados"]
               [:div {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights) :margin-top "4px"}}
                (or (:records_synced status) "—")]]
              [:div
               [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase"}}
                "Status"]
               [:div {:style {:margin-top "4px"}}
                [badge/badge {:variant (if (= (:status status) "OK") :success :error)}
                 (or (:status status) "—")]]]]

             ;; Counts breakdown
             (when (:counts status)
               [:div {:style {:padding "16px" :background t/bg-subtle :border-radius (:md t/border-radius)}}
                [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:semibold t/font-weights)}}
                 "Detalhes:"]
                [:div {:style {:margin-top "8px" :display "flex" :gap "16px" :flex-wrap "wrap"}}
                 (for [[k v] (:counts status)]
                   ^{:key k}
                   [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
                    (str (name k) ": " v)])]])

             ;; Errors
             (when (seq (:errors status))
               [:div
                [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:semibold t/font-weights) :color t/error-default}}
                 "Erros:"]
                [:ul {:style {:margin "8px 0 0" :padding-left "20px"}}
                 (for [e (:errors status)]
                   ^{:key e}
                   [:li {:style {:font-size (:sm t/font-sizes) :color t/error-dark}} e])]])]))]])))
