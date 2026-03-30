(ns app.views.finance.approval
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.tokens :as t]
            [app.auth.subs]))

(def sidebar-items
  [{:key :finance/dashboard :label "Dashboard"  :icon "💰" :route :finance/dashboard}
   {:key :finance/approval  :label "Aprovação"  :icon "✓"  :route :finance/approval}])

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(def approval-columns
  [{:key :ev_name          :label "EV"           :sortable true}
   {:key :quarter          :label "Período"      :sortable false
    :render (fn [row] (str "Q" (:quarter row) "/" (:year row)))}
   {:key :commission_total :label "Comissão Total" :sortable true
    :render (fn [row] (fmt-brl (:commission_total row)))}
   {:key :policies_count   :label "Negócios"    :sortable false}
   {:key :status           :label "Status"      :sortable false
    :render (fn [row] [badge/status-badge {:status (:status row)}])}
   {:key :actions          :label "Ações"        :sortable false
    :render (fn [row]
              [:div {:style {:display "flex" :gap "8px"}}
               [btn/button
                {:variant  :primary
                 :size     :sm
                 :on-click #(rf/dispatch [:finance/liberar-pagamento (:appraisal_id row)])}
                "Liberar Pagamento"]
               [btn/button
                {:variant  :secondary
                 :size     :sm
                 :on-click #(rf/dispatch [:finance/devolver (:appraisal_id row)])}
                "Devolver"]])}])

(defn approval-page []
  (rf/dispatch [:finance/fetch-approval])
  (fn []
    (let [items    @(rf/subscribe [:finance/approval-items])
          loading? @(rf/subscribe [:finance/approval-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items sidebar-items
        :current-route route
        :user          user
        :title         "Aprovação de Pagamentos"
        :subtitle      "Apurações aprovadas aguardando liberação"}

       [cards/card {}
        [tbl/data-table
         {:columns       approval-columns
          :rows          (or items [])
          :empty-message (if loading? "Carregando..." "Nenhuma apuração aguardando aprovação")}]]])))
