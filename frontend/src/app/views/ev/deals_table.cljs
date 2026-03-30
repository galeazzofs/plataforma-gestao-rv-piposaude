(ns app.views.ev.deals-table
  (:require [re-frame.core :as rf]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]))

(defn fmt-brl [v]
  (when v
    (let [n (if (string? v) (js/parseFloat v) v)]
      (str "R$ " (.toLocaleString n "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2})))))

(def columns
  [{:key :client_name  :label "Cliente"     :sortable true}
   {:key :benefit_type :label "Benefício"   :sortable false}
   {:key :segment      :label "Segmento"    :sortable false}
   {:key :mrr_projected :label "MRR"        :sortable true
    :render (fn [row] (fmt-brl (:mrr_projected row)))}
   {:key :commission_status :label "Status Comissão" :sortable false}
   {:key :mrr_for_commission :label "MRR Comissão"   :sortable true
    :render (fn [row] (fmt-brl (:mrr_for_commission row)))}
   {:key :installments_paid :label "Parcelas Pagas"  :sortable false
    :render (fn [row] (str (or (:installments_paid row) 0)))}
   {:key :hubspot_ticket_id :label "Ticket ID"       :sortable false}])

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
