(ns app.views.revops.policies
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when v
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (str "R$ " (.toLocaleString n "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))))

(def status-filter-options
  [{:value ""            :label "Todos os status"}
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

(defn installments-modal [_]
  (let [form (r/atom {:initial_installments_paid 0 :installments_paid 0})]
    (fn [{:keys [open? on-close policy-data]}]
      (let [init-val  (:initial_installments_paid @form)
            paid-val  (:installments_paid @form)]
        [modal/modal {:open?    open?
                      :on-close on-close
                      :title    (str "Parcelas — " (:client_name policy-data))
                      :size     :md}
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [:div {:style {:padding "12px 16px" :background t/bg-surface-raised
                         :border-radius "8px" :border (str "1px solid " t/border-default)}}
           [:div {:style {:font-size "13px" :color t/text-secondary :margin-bottom "4px"}}
            "Parcelas pré-plataforma"]
           [:div {:style {:font-size "13px" :color t/text-secondary}}
            "Quantas parcelas já foram pagas antes da plataforma existir? "
            "Ex: se 2 meses já foram pagos, restam 10 na plataforma."]]
          [inputs/input
           {:label     "Parcelas pré-plataforma"
            :type      "number"
            :value     (str init-val)
            :on-change #(let [v (js/parseInt % 10)
                              v (if (js/isNaN v) 0 (max 0 (min 12 v)))]
                          (swap! form assoc :initial_installments_paid v)
                          (when (< (:installments_paid @form) v)
                            (swap! form assoc :installments_paid v)))}]
          [inputs/input
           {:label     "Total de parcelas pagas"
            :type      "number"
            :value     (str paid-val)
            :on-change #(let [v (js/parseInt % 10)
                              v (if (js/isNaN v) 0 (max init-val (min 12 v)))]
                          (swap! form assoc :installments_paid v))}]
          [:div {:style {:font-size "13px" :color t/text-secondary}}
           (str "Restam " (- 12 paid-val) " parcelas a serem pagas na plataforma")]
          [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button
            {:variant  :primary
             :on-click (fn []
                         (rf/dispatch [:revops/update-policy-installments
                                       (:id policy-data)
                                       {:initial_installments_paid (:initial_installments_paid @form)
                                        :installments_paid         (:installments_paid @form)}])
                         (on-close))}
            "Salvar"]]]]))))

(defn make-columns [on-edit]
  [{:key :client_name      :label "Cliente"       :sortable true}
   {:key :hubspot_ticket_id :label "Ticket"       :sortable false :width "90px"}
   {:key :benefit_type     :label "Benefício"     :sortable true :width "90px"}
   {:key :segment          :label "Seg."          :sortable true :width "60px" :align "center"}
   {:key :mrr_for_commission :label "MRR"         :sortable true :align "right"
    :render (fn [row] (fmt-brl (:mrr_for_commission row)))}
   {:key :closed_date      :label "Data Gongo"    :sortable true :width "110px"}
   {:key :installments_paid :label "Parcelas"     :sortable false :width "100px" :align "center"
    :render (fn [row]
              (let [init (or (:initial_installments_paid row) 0)]
                [:span
                 (str (:installments_paid row) "/12")
                 (when (> init 0)
                   [:span {:style {:font-size "11px" :color t/text-secondary :margin-left "4px"}}
                    (str "(" init " pré)")])]))}
   {:key :commission_status :label "Status"       :sortable true :width "130px"
    :render (fn [row] [badge/status-badge {:status (:commission_status row)}])}
   {:key :actions :label "" :sortable false :width "70px"
    :render (fn [row]
              [btn/button {:variant :ghost :size :sm
                           :on-click #(on-edit row)}
               "Editar"])}])

(defn filters-bar [filters on-change]
  [:div {:style {:display "flex" :gap "12px" :align-items "flex-end"
                 :flex-wrap "wrap" :padding "0 0 16px"
                 :border-bottom (str "1px solid " t/border-default)
                 :margin-bottom "16px"}}
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
   [:div {:style {:padding-top "20px"}}
    [btn/button {:variant :ghost :size :sm
                 :on-click #(do (reset! filters {:status "" :segment "" :quarter "" :year "" :page 1})
                                (on-change))}
     "✕ Limpar filtros"]]])

(defn policies-page []
  (let [filters       (r/atom {:status "" :segment "" :quarter "" :year "" :page 1})
        modal-open?   (r/atom false)
        editing-policy (r/atom nil)]
    (rf/dispatch [:revops/fetch-policies @filters])
    (fn []
      (let [policies @(rf/subscribe [:revops/policies])
            meta     @(rf/subscribe [:revops/policies-meta])
            loading? @(rf/subscribe [:revops/policies-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            is-admin? (contains? #{"ADMIN" "GERENTE"} (:role user))
            fetch-fn #(rf/dispatch [:revops/fetch-policies
                                    (-> @filters
                                        (update :status (fn [v] (when-not (= v "") v)))
                                        (update :segment (fn [v] (when-not (= v "") v)))
                                        (update :quarter (fn [v] (when-not (= v "") v)))
                                        (update :year (fn [v] (when-not (= v "") v))))])
            cols     (if is-admin?
                       (make-columns (fn [row]
                                       (reset! editing-policy row)
                                       (reset! modal-open? true)))
                       (butlast (make-columns identity)))]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Apólices"
          :subtitle      (str (or (:total meta) 0) " apólices encontradas")}

         [cards/card {}
          [filters-bar filters fetch-fn]
          (if loading?
            [:div {:style {:padding "64px" :text-align "center"}}
             [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "8px"}}
              [:span {:style {:font-size "32px"}} "⏳"]
              [:span {:style {:color t/text-secondary}} "Carregando apólices..."]]]
            [tbl/data-table
             {:columns       cols
              :rows          (or policies [])
              :page          (:page meta)
              :total-pages   (:total_pages meta)
              :on-page-change (fn [p]
                                (swap! filters assoc :page p)
                                (fetch-fn))
              :empty-message "Nenhuma apólice encontrada"}])]

         (when is-admin?
           [installments-modal
            {:open?       @modal-open?
             :on-close    #(reset! modal-open? false)
             :policy-data @editing-policy}])]))))
