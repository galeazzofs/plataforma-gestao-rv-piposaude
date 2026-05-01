(ns app.views.ev.deals-table
  (:require [re-frame.core :as rf]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]
            [app.utils.format :as fmt]))

(def columns
  [{:key :client_name  :label "Cliente"          :sortable true}
   {:key :benefit_type :label "Benefício"         :sortable false}
   {:key :segment      :label "Seg."              :sortable false :width "60px"}
   {:key :mrr_projected :label "MRR"              :sortable true  :align "right"
    :render (fn [row] (fmt/fmt-brl (:mrr_projected row)))}
   {:key :mrr_for_commission :label "MRR Comissão" :sortable true  :align "right"
    :render (fn [row] (fmt/fmt-brl (:mrr_for_commission row)))}
   {:key :installments_paid :label "Parcelas"     :sortable false  :align "center" :width "80px"
    :render (fn [row] (str (or (:installments_paid row) 0)))}
   {:key :hubspot_ticket_id :label "Ticket"       :sortable false  :width "90px"}
   {:key :commission_status :label "Status"       :sortable false  :width "130px"
    :render (fn [row] [badge/status-badge {:status (:commission_status row)}])}])

(defn deals-table
  "Reusable deals/policies data table."
  [{:keys [rows loading? on-sort sort-key sort-order page total-pages on-page-change]}]
  [tbl/data-table
   {:columns       columns
    :rows          (or rows [])
    :on-sort       on-sort
    :sort-key      sort-key
    :sort-order    sort-order
    :page          page
    :total-pages   total-pages
    :on-page-change on-page-change
    :empty-message (if loading? "Carregando..." "Nenhum negócio encontrado")}])
