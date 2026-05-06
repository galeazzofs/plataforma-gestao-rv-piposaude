(ns app.ds.inputs
  (:require [app.ds.tokens :as t]
            [app.ds.typography :as typo]))

(defn- field-style [{:keys [error disabled]}]
  {:font-family t/font-body
   :font-size "14px"
   :padding "11px 14px"
   :border (str "1px solid " (if error t/error-default t/border-default))
   :border-radius (:sm t/border-radius)
   :background (if disabled t/bg-main t/bg-card)
   :color (if disabled t/text-disabled t/text-primary)
   :outline "none"
   :transition (str "box-shadow " t/transition-fast ", border-color " t/transition-fast)
   :width "100%"
   :box-sizing "border-box"})

(defn- short-id []
  (.substring (str (random-uuid)) 0 8))

(defn input
  "Text input.
   Props: value, on-change, placeholder, type, error, disabled, label, required, name, id."
  [_props]
  (let [generated-id (str "ds-input-" (short-id))]
    (fn [{:keys [value on-change placeholder type error disabled label required name id]}]
      (let [field-id (or id generated-id)
            err-id (str field-id "-err")]
        [:div {:style {:display "flex" :flex-direction "column" :gap "6px"}}
         (when label
           [typo/label {:for field-id :required required} label])
         [:input (cond-> {:id field-id
                          :style (field-style {:error error :disabled disabled})
                          :type (or type "text")
                          :value (or value "")
                          :name name
                          :placeholder placeholder
                          :disabled disabled
                          :required (boolean required)
                          :on-change #(when on-change (on-change (.. % -target -value)))}
                   error    (assoc :aria-invalid "true"
                                   :aria-describedby err-id)
                   required (assoc :aria-required "true"))]
         (when error
           [:span {:id err-id
                   :role "alert"
                   :style {:font-size "11px" :color t/error-default
                           :font-family t/font-mono}}
            error])]))))

(defn select
  "Select dropdown.
   options: [{:value \"x\" :label \"X\"} ...]"
  [_props]
  (let [generated-id (str "ds-select-" (short-id))]
    (fn [{:keys [value on-change options label required disabled error id]}]
      (let [field-id (or id generated-id)
            err-id (str field-id "-err")]
        [:div {:style {:display "flex" :flex-direction "column" :gap "6px"}}
         (when label
           [typo/label {:for field-id :required required} label])
         [:select (cond-> {:id field-id
                           :style (assoc (field-style {:error error :disabled disabled})
                                         :cursor "pointer" :appearance "auto")
                           :value (or value "")
                           :disabled disabled
                           :required (boolean required)
                           :on-change #(when on-change (on-change (.. % -target -value)))}
                    error    (assoc :aria-invalid "true"
                                    :aria-describedby err-id)
                    required (assoc :aria-required "true"))
          (for [{:keys [value label]} options]
            ^{:key value}
            [:option {:value value} label])]
         (when error
           [:span {:id err-id
                   :role "alert"
                   :style {:font-size "11px" :color t/error-default
                           :font-family t/font-mono}}
            error])]))))

(defn file-upload
  "File upload dropzone for XLSX. Mirrors the .dropzone style from the design.
   The visible text inside the <label> becomes the input's accessible name."
  [_props]
  (let [input-id (str "ds-file-" (short-id))]
    (fn [{:keys [on-file accept label]}]
      [:div {:style {:display "flex" :flex-direction "column" :gap "6px"}}
       (when label
         [typo/label {:for input-id} label])
       [:label {:html-for input-id
                :style {:display "flex"
                        :align-items "center"
                        :justify-content "center"
                        :padding "48px 24px"
                        :border (str "2px dashed " t/border-default)
                        :border-radius (:md t/border-radius)
                        :background t/bg-surface
                        :cursor "pointer"
                        :transition (str "all " t/transition-fast)
                        :text-align "center"}}
        [:input {:id input-id
                 :type "file"
                 :accept (or accept ".xlsx,.xls")
                 :style {:display "none"}
                 :on-change #(when on-file
                               (let [file (-> % .-target .-files (aget 0))]
                                 (when file (on-file file))))}]
        [:div {:style {:display "flex" :flex-direction "column" :gap "10px" :align-items "center"
                       :color t/text-tertiary}}
         [:svg {:width "36" :height "36" :aria-hidden true
                :style {:color t/border-hover}}
          [:use {:href "#i-upload"}]]
         [:strong {:style {:font-family t/font-heading :color t/text-primary
                           :font-size "15px" :font-weight (:semibold t/font-weights)}}
          "Clique ou arraste o arquivo aqui"]
         [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary}}
          "Formatos aceitos: .xlsx, .xls"]]]])))
