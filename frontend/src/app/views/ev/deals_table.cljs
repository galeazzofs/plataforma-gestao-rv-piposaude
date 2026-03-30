(ns app.views.ev.deals-table
  (:require [re-frame.core :as rf]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]))

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(def columns
  [{:key :client_name  :label "Cliente"     :sortable true}
   {:key :benefit_type :label "Benefício"   :sortable false}
   {:key :segment      :label "Segmento"    :sortable false}
   {:key :mrr          :label "MRR"         :sortable true
    :render (fn [row] (fmt-brl (:mrr row)))}
   {:key :commission_pct :label "%"         :sortable false
    :render (fn [row] (when-let [p (:commission_pct row)] (str (.toFixed p 1) "%")))}
   {:key :commission_monthly :label "Comissão/mês" :sortable true
    :render (fn [row] (fmt-brl (:commission_monthly row)))}
   {:key :installments :label "Parcelas"    :sortable false
    :render (fn [row]
              (let [current (or (:installment_current row) 0)
                    total   (or (:installment_total row) 12)]
                (str current "/" total)))}
   {:key :status :label "Status" :sortable false
    :render (fn [row] [badge/status-badge {:status (:status row)}])}])

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
