(ns app.views.revops.financial-upload
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(def preview-columns
  [{:key :client_name  :label "Cliente"   :sortable false}
   {:key :mrr          :label "MRR"       :sortable false :align "right"}
   {:key :operation    :label "Operação"  :sortable false :width "110px"
    :render (fn [row]
              (let [op (:operation row)]
                [badge/badge {:variant (case op "NEW" :success "UPDATED" :info "ERROR" :error :default)}
                 (case op "NEW" "Novo" "UPDATED" "Atualizado" "ERROR" "Erro" op)]))}
   {:key :message      :label "Mensagem"  :sortable false}])

(defn upload-step []
  [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
   [:div {:style {:display "flex" :gap "16px" :padding "16px" :background t/beige-100
                  :border-radius (:md t/border-radius) :align-items "flex-start"}}
    [:span {:style {:font-size "20px"}} "ℹ️"]
    [:p {:style {:color t/text-secondary :margin "0" :font-size (:sm t/font-sizes) :line-height "1.6"}}
     "Faça upload do arquivo XLSX com os dados financeiros. O sistema irá processar e mostrar um preview antes de confirmar o envio."]]
   [inputs/file-upload
    {:label   "Arquivo Financeiro (.xlsx)"
     :accept  ".xlsx,.xls"
     :on-file #(rf/dispatch [:revops/upload-financial %])}]])

(defn preview-step [preview]
  (let [items  (:items preview)
        counts (:counts preview)
        upload-id (:upload_id preview)]
    [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
     ;; Summary row
     [:div {:style {:display "flex" :gap "12px" :padding "16px" :background t/bg-main
                    :border-radius (:md t/border-radius)}}
      [:div {:style {:display "flex" :align-items "center" :gap "8px"}}
       [badge/badge {:variant :success} (str (:new counts 0) " novos")]
       [badge/badge {:variant :info}    (str (:updated counts 0) " atualizados")]
       [badge/badge {:variant :error}   (str (:errors counts 0) " erros")]]]

     ;; Preview table
     [tbl/data-table
      {:columns       preview-columns
       :rows          (or items [])
       :empty-message "Nenhum item no preview"}]

     ;; Actions
     [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"
                    :padding-top "16px" :border-top (str "1px solid " t/border-default)}}
      [btn/button {:variant :secondary
                   :on-click #(rf/dispatch [:revops/upload-preview-cancel])}
       "Cancelar"]
      [btn/button {:variant  :primary
                   :disabled (> (or (:errors counts) 0) 0)
                   :on-click #(rf/dispatch [:revops/confirm-financial-upload upload-id])}
       "Confirmar Upload"]]]))

(defn financial-upload-page []
  (fn []
    (let [preview  @(rf/subscribe [:revops/upload-preview])
          loading? @(rf/subscribe [:revops/upload-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items revops-shell/sidebar-items
        :current-route route
        :user          user
        :title         "Upload Financeiro"
        :subtitle      "Importar dados financeiros via XLSX"}

       [cards/card {}
        (cond
          loading?
          [:div {:style {:padding "64px" :text-align "center"}}
           [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "12px"}}
            [:span {:style {:font-size "40px"}} "⚙️"]
            [:span {:style {:color t/text-secondary :font-size (:base t/font-sizes) :font-weight (:medium t/font-weights)}} "Processando arquivo..."]
            [:span {:style {:color t/text-disabled :font-size (:sm t/font-sizes)}} "Aguarde, isso pode levar alguns segundos."]]]

          preview
          [preview-step preview]

          :else
          [upload-step])]])))
