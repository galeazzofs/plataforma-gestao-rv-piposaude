(ns app.views.revops.audit-log
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(def table-options
  [{:value "" :label "Todas as tabelas"}
   {:value "policies"    :label "Políticas"}
   {:value "commissions" :label "Comissões"}
   {:value "appraisals"  :label "Apurações"}
   {:value "users"       :label "Usuários"}
   {:value "settings"    :label "Configurações"}])

(def audit-columns
  [{:key :created_at :label "Data/Hora" :sortable true}
   {:key :user_name  :label "Usuário"   :sortable false}
   {:key :table_name :label "Tabela"    :sortable false}
   {:key :action     :label "Ação"      :sortable false}
   {:key :row_id     :label "ID"        :sortable false}
   {:key :changes    :label "Alterações" :sortable false
    :render (fn [row]
              [:code {:style {:font-size (:xs t/font-sizes)
                              :background t/bg-subtle
                              :padding "2px 6px"
                              :border-radius (:sm t/border-radius)
                              :max-width "300px"
                              :display "block"
                              :overflow "hidden"
                              :text-overflow "ellipsis"
                              :white-space "nowrap"}}
               (js/JSON.stringify (clj->js (or (:changes row) {})))])}])

(defn audit-log-page []
  (let [filters (r/atom {:from nil :to nil :table nil :user nil})]
    (rf/dispatch [:revops/fetch-audit-log @filters])
    (fn []
      (let [audit-log @(rf/subscribe [:revops/audit-log])
            loading?  @(rf/subscribe [:revops/audit-loading?])
            user      @(rf/subscribe [:auth/current-user])
            route     @(rf/subscribe [:current-route-name])
            items     (or (:items audit-log) [])
            meta      (:meta audit-log)]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Audit Log"
          :subtitle      "Rastreio de todas as alterações na plataforma"}

         ;; Filter bar
         [cards/card {:style {:margin-bottom "24px"}}
          [:div {:style {:display "flex" :gap "16px" :align-items "flex-end" :flex-wrap "wrap"}}
           [:div {:style {:flex "1" :min-width "140px"}}
            [inputs/input
             {:label     "Data inicial"
              :type      "date"
              :value     (or (:from @filters) "")
              :on-change #(swap! filters assoc :from (when-not (clojure.string/blank? %) %))}]]
           [:div {:style {:flex "1" :min-width "140px"}}
            [inputs/input
             {:label     "Data final"
              :type      "date"
              :value     (or (:to @filters) "")
              :on-change #(swap! filters assoc :to (when-not (clojure.string/blank? %) %))}]]
           [:div {:style {:flex "1" :min-width "140px"}}
            [inputs/select
             {:label     "Tabela"
              :value     (or (:table @filters) "")
              :options   table-options
              :on-change #(swap! filters assoc :table (when-not (clojure.string/blank? %) %))}]]
           [:div {:style {:flex "1" :min-width "140px"}}
            [inputs/input
             {:label       "Usuário"
              :value       (or (:user @filters) "")
              :placeholder "Nome ou e-mail"
              :on-change   #(swap! filters assoc :user (when-not (clojure.string/blank? %) %))}]]
           [btn/button {:variant :primary
                        :on-click #(rf/dispatch [:revops/fetch-audit-log @filters])}
            "Filtrar"]]]

         ;; Table
         [cards/card {}
          [tbl/data-table
           {:columns        audit-columns
            :rows           items
            :page           (or (:page meta) 1)
            :total-pages    (or (:total_pages meta) 1)
            :on-page-change (fn [p] (rf/dispatch [:revops/fetch-audit-log (assoc @filters :page p)]))
            :empty-message  (if loading? "Carregando..." "Nenhum registro encontrado")}]]]))))
