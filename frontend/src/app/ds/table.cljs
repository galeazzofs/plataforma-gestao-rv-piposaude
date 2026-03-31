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
     [:tr {:style {:background t/bg-main
                   :border-bottom (str "1px solid " t/border-default)}}
      (for [{:keys [key label sortable width align]} columns]
        ^{:key key}
        [:th {:style {:padding "10px 16px"
                      :text-align (or align "left")
                      :font-weight (:semibold t/font-weights)
                      :color t/text-secondary
                      :font-size (:xs t/font-sizes)
                      :text-transform "uppercase"
                      :letter-spacing "0.06em"
                      :cursor (when sortable "pointer")
                      :width width
                      :white-space "nowrap"
                      :user-select "none"}
              :on-click (when (and sortable on-sort)
                          #(on-sort key))}
         [:span {:style {:display "inline-flex" :align-items "center" :gap "4px"}}
          label
          (when (and sortable (= sort-key key))
            [:span {:style {:color t/color-primary}}
             (if (= sort-order :asc) " ↑" " ↓")])]
         (when (and sortable (not= sort-key key))
           [:span {:style {:color t/text-disabled :margin-left "2px"}} "↕"])])]]
    [:tbody
     (if (empty? rows)
       [:tr [:td {:col-span (count columns)
                  :style {:padding "64px 16px"
                          :text-align "center"}}
             [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "8px"}}
              [:span {:style {:font-size "32px"}} "📭"]
              [:span {:style {:color t/text-secondary :font-size (:sm t/font-sizes)}}
               (or empty-message "Nenhum dado encontrado")]]]]
       (map-indexed
        (fn [idx row]
          ^{:key (or (:id row) (hash row))}
          [:tr {:style {:border-bottom (str "1px solid " t/border-default)
                        :background (if (odd? idx) t/bg-card "rgba(247,246,243,0.5)")
                        :transition (str "background " t/transition-fast)}}
           (for [{:keys [key render align]} columns]
             ^{:key (str (or (:id row) idx) "-" key)}
             [:td {:style {:padding "12px 16px" :color t/text-primary
                           :text-align (or align "left")
                           :vertical-align "middle"}}
              (if render
                (render row)
                (get row key))])])
        rows))]]
   ;; Pagination
   (when (and page total-pages (> total-pages 1))
     [:div {:style {:display "flex"
                    :justify-content "space-between"
                    :align-items "center"
                    :padding "16px 0"
                    :border-top (str "1px solid " t/border-default)
                    :margin-top "4px"}}
      [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
       (str "Página " page " de " total-pages)]
      [:div {:style {:display "flex" :gap "6px"}}
       [:button {:style {:padding "6px 14px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:md t/border-radius)
                         :background t/bg-card
                         :font-size (:sm t/font-sizes)
                         :cursor (if (> page 1) "pointer" "not-allowed")
                         :opacity (if (> page 1) "1" "0.4")
                         :transition (str "all " t/transition-fast)}
                 :disabled (<= page 1)
                 :on-click #(when (> page 1) (on-page-change (dec page)))}
        "← Anterior"]
       [:button {:style {:padding "6px 14px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:md t/border-radius)
                         :background t/bg-card
                         :font-size (:sm t/font-sizes)
                         :cursor (if (< page total-pages) "pointer" "not-allowed")
                         :opacity (if (< page total-pages) "1" "0.4")
                         :transition (str "all " t/transition-fast)}
                 :disabled (>= page total-pages)
                 :on-click #(when (< page total-pages) (on-page-change (inc page)))}
        "Próxima →"]]])])
