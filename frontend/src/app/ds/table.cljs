(ns app.ds.table
  (:require [app.ds.tokens :as t]))

(defn data-table
  "Data table with sort, pagination.
   columns: [{:key :name :label \"Name\" :sortable true :render fn} ...]
   rows: [{:id 1 :name \"X\"} ...]
   Props: on-sort, sort-key, sort-order, page, total-pages, on-page-change"
  [{:keys [columns rows on-sort sort-key sort-order
           page total-pages on-page-change empty-message]}]
  [:div {:style {:overflow-x "auto"}}
   [:table {:style {:width "100%"
                    :border-collapse "collapse"
                    :font-size (:sm t/font-sizes)}}
    [:thead
     [:tr {:style {:border-bottom (str "2px solid " t/border-default)}}
      (for [{:keys [key label sortable width]} columns]
        ^{:key key}
        [:th {:style {:padding "12px 16px"
                      :text-align "left"
                      :font-weight (:semibold t/font-weights)
                      :color t/text-secondary
                      :font-size (:xs t/font-sizes)
                      :text-transform "uppercase"
                      :letter-spacing "0.05em"
                      :cursor (when sortable "pointer")
                      :width width
                      :user-select "none"}
              :on-click (when (and sortable on-sort)
                          #(on-sort key))}
         label
         (when (and sortable (= sort-key key))
           [:span {:style {:margin-left "4px"}}
            (if (= sort-order :asc) "↑" "↓")])])]]
    [:tbody
     (if (empty? rows)
       [:tr [:td {:col-span (count columns)
                  :style {:padding "48px 16px"
                          :text-align "center"
                          :color t/text-disabled}}
             (or empty-message "Nenhum dado encontrado")]]
       (for [row rows]
         ^{:key (or (:id row) (hash row))}
         [:tr {:style {:border-bottom (str "1px solid " t/bg-subtle)
                       :transition t/transition-fast}}
          (for [{:keys [key render]} columns]
            ^{:key (str (:id row) "-" key)}
            [:td {:style {:padding "12px 16px" :color t/text-primary}}
             (if render
               (render row)
               (get row key))])]))]]
   ;; Pagination
   (when (and page total-pages (> total-pages 1))
     [:div {:style {:display "flex"
                    :justify-content "space-between"
                    :align-items "center"
                    :padding "16px 0"}}
      [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
       (str "Página " page " de " total-pages)]
      [:div {:style {:display "flex" :gap "8px"}}
       [:button {:style {:padding "6px 12px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:md t/border-radius)
                         :background t/bg-card
                         :cursor (if (> page 1) "pointer" "not-allowed")
                         :opacity (if (> page 1) "1" "0.5")}
                 :disabled (<= page 1)
                 :on-click #(when (> page 1) (on-page-change (dec page)))}
        "Anterior"]
       [:button {:style {:padding "6px 12px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:md t/border-radius)
                         :background t/bg-card
                         :cursor (if (< page total-pages) "pointer" "not-allowed")
                         :opacity (if (< page total-pages) "1" "0.5")}
                 :disabled (>= page total-pages)
                 :on-click #(when (< page total-pages) (on-page-change (inc page)))}
        "Próxima"]]])])
