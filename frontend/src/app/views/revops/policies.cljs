(ns app.views.revops.policies
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.views.revops.policy-edit-modal :as edit-modal]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when v
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (str "R$ " (.toLocaleString n "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))))

(def status-filter-options
  [{:value ""            :label "Todos"}
   {:value "PROJECTED"   :label "Projetado"}
   {:value "IN_PAYMENT"  :label "Em Pagamento"}
   {:value "SETTLED"     :label "Quitado"}
   {:value "CANCELLED"   :label "Cancelado"}])

(def segment-filter-options
  [{:value "" :label "Todos"}
   {:value "PP" :label "PP"}
   {:value "P"  :label "P"}
   {:value "M"  :label "M"}
   {:value "G"  :label "G"}])

(defn build-columns [open-edit]
  [{:key :client_name      :label "Cliente"       :sortable true}
   {:key :hubspot_ticket_id :label "Ticket"       :sortable false :width "100px"}
   {:key :benefit_type     :label "Benefício"     :sortable true :width "90px"}
   {:key :segment          :label "Segmento"      :sortable true :width "80px"}
   {:key :mrr_for_commission :label "MRR"         :sortable true
    :render (fn [row] (fmt-brl (:mrr_for_commission row)))}
   {:key :closed_date      :label "Data Gongo"    :sortable true :width "110px"}
   {:key :installments_paid :label "Parcelas"     :sortable false :width "80px"
    :render (fn [row] (str (:installments_paid row) "/12"))}
   {:key :commission_status :label "Status"       :sortable true :width "120px"
    :render (fn [row] [badge/status-badge {:status (:commission_status row)}])}
   {:key :edit :label "" :sortable false :width "90px"
    :render (fn [row]
              [btn/button {:variant :secondary :size :sm
                           :on-click #(open-edit row)}
               "✏️ Editar"])}])

(defn filters-bar [filters on-change]
  [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :flex-wrap "wrap" :margin-bottom "16px"}}
   [:div {:style {:width "200px"}}
    [inputs/select {:label "Status"
                    :value (or (:status @filters) "")
                    :options status-filter-options
                    :on-change #(do (swap! filters assoc :status %)
                                    (on-change))}]]
   [:div {:style {:width "120px"}}
    [inputs/select {:label "Segmento"
                    :value (or (:segment @filters) "")
                    :options segment-filter-options
                    :on-change #(do (swap! filters assoc :segment %)
                                    (on-change))}]]
   [:div {:style {:width "100px"}}
    [inputs/input {:label "Trimestre"
                   :type "number"
                   :placeholder "1-4"
                   :value (or (:quarter @filters) "")
                   :on-change #(do (swap! filters assoc :quarter %)
                                    (on-change))}]]
   [:div {:style {:width "100px"}}
    [inputs/input {:label "Ano"
                   :type "number"
                   :placeholder "2026"
                   :value (or (:year @filters) "")
                   :on-change #(do (swap! filters assoc :year %)
                                    (on-change))}]]
   [btn/button {:variant :ghost :size :sm
                :on-click #(do (reset! filters {:status "" :segment "" :quarter "" :year "" :page 1})
                               (on-change))}
    "Limpar filtros"]])

(defn policies-page []
  (let [filters (r/atom {:status "" :segment "" :quarter "" :year "" :page 1})
        modal-open? (r/atom false)
        selected-policy (r/atom nil)
        open-edit (fn [row]
                    (reset! selected-policy row)
                    (reset! modal-open? true))
        close-edit #(reset! modal-open? false)]
    (rf/dispatch [:revops/fetch-policies @filters])
    (fn []
      (let [policies @(rf/subscribe [:revops/policies])
            meta     @(rf/subscribe [:revops/policies-meta])
            loading? @(rf/subscribe [:revops/policies-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            fetch-fn #(rf/dispatch [:revops/fetch-policies
                                    (-> @filters
                                        (update :status (fn [v] (when-not (= v "") v)))
                                        (update :segment (fn [v] (when-not (= v "") v)))
                                        (update :quarter (fn [v] (when-not (= v "") v)))
                                        (update :year (fn [v] (when-not (= v "") v))))])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Apólices"
          :subtitle      (str (or (:total meta) 0) " apólices encontradas")}

         [cards/card {}
          [filters-bar filters fetch-fn]
          (if loading?
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Carregando..."]
            [tbl/data-table
             {:columns       (build-columns open-edit)
              :rows          (or policies [])
              :page          (:page meta)
              :total-pages   (:total_pages meta)
              :on-page-change (fn [p]
                                (swap! filters assoc :page p)
                                (fetch-fn))
              :empty-message "Nenhuma apólice encontrada"}])]

         [edit-modal/policy-edit-modal
          {:open? @modal-open?
           :policy @selected-policy
           :on-close close-edit}]]))))
