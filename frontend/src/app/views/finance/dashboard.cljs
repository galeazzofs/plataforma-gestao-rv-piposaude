(ns app.views.finance.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.views.finance.saldo-devedor :as saldo-devedor]
            [app.views.finance.fluxo-caixa :as fluxo-caixa]
            [app.views.finance.orcado-realizado :as orcado-realizado]
            [app.views.finance.export :as export-panel]
            [app.auth.subs]))

(def sidebar-items
  [{:key :finance/dashboard :label "Dashboard"  :icon "💰" :route :finance/dashboard}
   {:key :finance/approval  :label "Aprovação"  :icon "✓"  :route :finance/approval}])

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(def ev-columns
  [{:key :ev_name          :label "EV"           :sortable true}
   {:key :commission_total :label "Comissão"     :sortable true
    :render (fn [row] (fmt-brl (:commission_total row)))}
   {:key :achievement_pct  :label "Atingimento"  :sortable true
    :render (fn [row]
              (let [pct (or (:achievement_pct row) 0)
                    color (cond (>= pct 100) t/success-default
                                (>= pct 50)  t/warning-default
                                :else        t/error-default)]
                [:span {:style {:color color :font-weight (:semibold t/font-weights)}}
                 (str (.toFixed pct 1) "%")]))}
   {:key :status           :label "Status"       :sortable false
    :render (fn [row] [badge/status-badge {:status (:appraisal_status row)}])}
   {:key :actions          :label ""             :sortable false
    :render (fn [row]
              [btn/button
               {:variant  :ghost
                :size     :sm
                :on-click #(rf/dispatch [:navigate! [:gerente/ev-detail {:ev-id (:ev_id row)}]])}
               "Ver detalhes →"])}])

(defn finance-dashboard-page []
  (rf/dispatch [:finance/fetch-dashboard])
  (fn []
    (let [dashboard @(rf/subscribe [:finance/dashboard])
          loading?  @(rf/subscribe [:finance/loading?])
          user      @(rf/subscribe [:auth/current-user])
          route     @(rf/subscribe [:current-route-name])
          saldo-total       (or (:saldo_devedor_total dashboard) 0)
          saldo-years       (or (:saldo_by_year dashboard) [])
          fluxo-data        (or (:fluxo_caixa dashboard) [])
          orcado-data       (or (:orcado_realizado dashboard) [])
          ev-summary        (or (:ev_summary dashboard) [])]
      [layout/page-shell
       {:sidebar-items sidebar-items
        :current-route route
        :user          user
        :title         "Finance Dashboard"
        :subtitle      "Visão financeira consolidada"}

       ;; Saldo total
       (if loading?
         [:div {:style {:color t/text-secondary :margin-bottom "32px"}} "Carregando..."]
         [:div {:style {:margin-bottom "32px"}}
          [cards/stat-card
           {:label    "Saldo Devedor Total"
            :value    (fmt-brl saldo-total)
            :subtitle "Todas as comissões em aberto"
            :color    :default}]])

       ;; Saldo por ano
       (when-not loading?
         [:div {:style {:margin-bottom "32px"}}
          [cards/card {}
           [saldo-devedor/saldo-by-year saldo-years]]])

       ;; Charts row
       (when-not loading?
         [:div {:style {:display "grid" :grid-template-columns "1fr 1fr" :gap "24px" :margin-bottom "32px"}}
          [cards/card {}
           [fluxo-caixa/fluxo-caixa-chart fluxo-data]]
          [cards/card {}
           [orcado-realizado/orcado-realizado-chart orcado-data]]])

       ;; EV Table
       (when-not loading?
         [:div {:style {:margin-bottom "32px"}}
          [cards/card {}
           [:h3 {:style {:font-size (:lg t/font-sizes)
                         :font-weight (:semibold t/font-weights)
                         :margin-bottom "16px"}} "Resumo por EV"]
           [tbl/data-table
            {:columns       ev-columns
             :rows          ev-summary
             :empty-message "Nenhum dado disponível"}]]])

       ;; Export
       [export-panel/export-panel]])))
